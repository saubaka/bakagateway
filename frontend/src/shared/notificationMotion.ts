export const NOTIFICATION_SCHEMA_VERSION = 1 as const;
export const NOTIFICATION_TYPES = ['success', 'info', 'warning', 'error', 'loading'] as const;
export type NotificationType = typeof NOTIFICATION_TYPES[number];
export type NotificationTiming = { enterMs: number; exitMs: number; textOutMs: number; textInMs: number };
export type NotificationMotionConfig = {
  types: Record<NotificationType, NotificationTiming>;
  stackMs: number;
};
export type UiConfig = {
  schemaVersion: typeof NOTIFICATION_SCHEMA_VERSION;
  revision: number;
  notificationMotion: NotificationMotionConfig;
};
export const NOTIFICATION_TIMING_LIMITS = { enterMs: 3000, exitMs: 3000, textOutMs: 1000, textInMs: 1000 } as const;
export const NOTIFICATION_STACK_LIMIT = 1500;

export function defaultUiConfig(): UiConfig {
  const types = {} as Record<NotificationType, NotificationTiming>;
  for (const type of NOTIFICATION_TYPES) types[type] = { enterMs: 780, exitMs: 680, textOutMs: 160, textInMs: 340 };
  return { schemaVersion: NOTIFICATION_SCHEMA_VERSION, revision: 0, notificationMotion: { types, stackMs: 320 } };
}

function exactObject(value: unknown, keys: readonly string[]): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
}
function integer(value: unknown, max: number): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 && value <= max;
}

export function isUiConfig(value: unknown): value is UiConfig {
  if (!exactObject(value, ['schemaVersion', 'revision', 'notificationMotion'])
    || value.schemaVersion !== NOTIFICATION_SCHEMA_VERSION || !integer(value.revision, Number.MAX_SAFE_INTEGER)) return false;
  const motion = value.notificationMotion;
  if (!exactObject(motion, ['types', 'stackMs']) || !integer(motion.stackMs, NOTIFICATION_STACK_LIMIT)
    || !exactObject(motion.types, NOTIFICATION_TYPES)) return false;
  for (const type of NOTIFICATION_TYPES) {
    const timing = motion.types[type];
    if (!exactObject(timing, Object.keys(NOTIFICATION_TIMING_LIMITS))) return false;
    for (const key of Object.keys(NOTIFICATION_TIMING_LIMITS) as (keyof NotificationTiming)[]) {
      if (!integer(timing[key], NOTIFICATION_TIMING_LIMITS[key])) return false;
    }
  }
  return true;
}

export function copyUiConfig(value: UiConfig): UiConfig {
  const types = {} as Record<NotificationType, NotificationTiming>;
  for (const type of NOTIFICATION_TYPES) {
    const { enterMs, exitMs, textOutMs, textInMs } = value.notificationMotion.types[type];
    types[type] = { enterMs, exitMs, textOutMs, textInMs };
  }
  return { schemaVersion: value.schemaVersion, revision: value.revision,
    notificationMotion: { types, stackMs: value.notificationMotion.stackMs } };
}
