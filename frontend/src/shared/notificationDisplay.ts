import {
  copyUiConfig, defaultUiConfig, isUiConfig, NOTIFICATION_SCHEMA_VERSION, NOTIFICATION_TYPES,
  type NotificationMotionConfig, type NotificationType, type UiConfig,
} from './notificationMotion.ts';

export const NOTIFICATION_DISPLAY_SCHEMA_VERSION = 2 as const;
export const NOTIFICATION_DISPLAY_DURATION_LIMITS = Object.freeze({ minMs: 1000, maxMs: 120000, stepMs: 1000 });
export const DEFAULT_TIMED_DISPLAY_MS: Readonly<Record<NotificationType, number>> = Object.freeze({
  success: 5000, info: 6000, warning: 8000, error: 10000, loading: 15000,
});

export type ResultDisplayPolicy = { mode: 'timed'; durationMs: number } | { mode: 'manual' };
export type LoadingDisplayPolicy = { mode: 'untilSettled' } | { mode: 'timedHide'; durationMs: number };
export type NotificationDisplayConfig = {
  types: Record<Exclude<NotificationType, 'loading'>, ResultDisplayPolicy> & { loading: LoadingDisplayPolicy };
};
export type UiConfigV2 = {
  schemaVersion: typeof NOTIFICATION_DISPLAY_SCHEMA_VERSION;
  revision: number;
  notificationMotion: NotificationMotionConfig;
  notificationDisplay: NotificationDisplayConfig;
};

export function defaultNotificationDisplay(): NotificationDisplayConfig {
  return { types: {
    success: { mode: 'timed', durationMs: DEFAULT_TIMED_DISPLAY_MS.success },
    info: { mode: 'timed', durationMs: DEFAULT_TIMED_DISPLAY_MS.info },
    warning: { mode: 'timed', durationMs: DEFAULT_TIMED_DISPLAY_MS.warning },
    error: { mode: 'manual' }, loading: { mode: 'untilSettled' },
  } };
}

function exactObject(value: unknown, keys: readonly string[]): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    && Reflect.ownKeys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
}
function validDuration(value: unknown): value is number {
  const { minMs, maxMs, stepMs } = NOTIFICATION_DISPLAY_DURATION_LIMITS;
  return typeof value === 'number' && Number.isSafeInteger(value)
    && value >= minMs && value <= maxMs && value % stepMs === 0;
}
function validPolicy(value: unknown, loading: boolean): boolean {
  const indefinite = loading ? 'untilSettled' : 'manual', timed = loading ? 'timedHide' : 'timed';
  return (exactObject(value, ['mode']) && value.mode === indefinite)
    || (exactObject(value, ['mode', 'durationMs']) && value.mode === timed && validDuration(value.durationMs));
}
export function isNotificationDisplay(value: unknown): value is NotificationDisplayConfig {
  if (!exactObject(value, ['types']) || !exactObject(value.types, NOTIFICATION_TYPES)) return false;
  const types = value.types;
  return NOTIFICATION_TYPES.every(type => validPolicy(types[type], type === 'loading'));
}

function copyResultPolicy(value: ResultDisplayPolicy): ResultDisplayPolicy {
  return value.mode === 'timed' ? { mode: value.mode, durationMs: value.durationMs } : { mode: value.mode };
}
function copyLoadingPolicy(value: LoadingDisplayPolicy): LoadingDisplayPolicy {
  return value.mode === 'timedHide' ? { mode: value.mode, durationMs: value.durationMs } : { mode: value.mode };
}
export function copyNotificationDisplay(value: NotificationDisplayConfig): NotificationDisplayConfig {
  return { types: {
    success: copyResultPolicy(value.types.success), info: copyResultPolicy(value.types.info),
    warning: copyResultPolicy(value.types.warning), error: copyResultPolicy(value.types.error),
    loading: copyLoadingPolicy(value.types.loading),
  } };
}

function legacyFields(value: { revision: number; notificationMotion: NotificationMotionConfig }): UiConfig {
  return { schemaVersion: NOTIFICATION_SCHEMA_VERSION, revision: value.revision, notificationMotion: value.notificationMotion };
}
export function defaultUiConfigV2(): UiConfigV2 {
  const legacy = defaultUiConfig();
  return { schemaVersion: NOTIFICATION_DISPLAY_SCHEMA_VERSION, revision: legacy.revision,
    notificationMotion: legacy.notificationMotion, notificationDisplay: defaultNotificationDisplay() };
}
export function isUiConfigV2(value: unknown): value is UiConfigV2 {
  if (!exactObject(value, ['schemaVersion', 'revision', 'notificationMotion', 'notificationDisplay'])
    || value.schemaVersion !== NOTIFICATION_DISPLAY_SCHEMA_VERSION) return false;
  return isUiConfig({ schemaVersion: NOTIFICATION_SCHEMA_VERSION, revision: value.revision,
    notificationMotion: value.notificationMotion }) && isNotificationDisplay(value.notificationDisplay);
}
export function copyUiConfigV2(value: UiConfigV2): UiConfigV2 {
  const legacy = copyUiConfig(legacyFields(value));
  return { schemaVersion: NOTIFICATION_DISPLAY_SCHEMA_VERSION, revision: legacy.revision,
    notificationMotion: legacy.notificationMotion, notificationDisplay: copyNotificationDisplay(value.notificationDisplay) };
}
export function upgradeUiConfigV1(value: unknown): UiConfigV2 | null {
  if (!isUiConfig(value)) return null;
  const legacy = copyUiConfig(value);
  return { schemaVersion: NOTIFICATION_DISPLAY_SCHEMA_VERSION, revision: legacy.revision,
    notificationMotion: legacy.notificationMotion, notificationDisplay: defaultNotificationDisplay() };
}
export function normalizeUiConfigV2(value: unknown): UiConfigV2 | null {
  return isUiConfigV2(value) ? copyUiConfigV2(value) : upgradeUiConfigV1(value);
}
export function projectUiConfigV1(value: UiConfigV2): UiConfig {
  return copyUiConfig(legacyFields(value));
}
export function applyLegacyMotionEdit(current: UiConfigV2, input: unknown): UiConfigV2 | null {
  if (!isUiConfigV2(current) || !isUiConfig(input) || input.revision !== current.revision) return null;
  const next = copyUiConfigV2(current);
  next.notificationMotion = copyUiConfig(input).notificationMotion;
  return next;
}
