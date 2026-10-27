import type { NotificationType, UiConfig } from './shared/notificationMotion.ts';
import { normalizeUiConfigV2, type UiConfigV2 } from './shared/notificationDisplay.ts';
import { snapshotUiConfigV2 } from './notificationConfig.ts';
import { notificationTimeline, waitForNoticeAnimation, waitForNoticeTransition, type PhaseJob } from './notificationTiming.ts';
import { createNotificationDisplayTimer, type NotificationDisplayClock } from './notificationDisplayTiming.ts';
export type NotificationTone = 'success' | 'info' | 'warning' | 'error';
type ProgressState = { message?: string; updateMessage?: string; version: number; tone?: NotificationTone; settled: boolean;
  canceled?: boolean; listeners: Set<() => void>; owner?: ProgressOwner };
export type NoticeOptions = { manualReason?: 'delivery-unconfirmed'; action?: { label: string; run: () => void | Promise<void> };
  previewConfig?: UiConfig | UiConfigV2; signal?: AbortSignal; clock?: NotificationDisplayClock };
export type Notification = { message: string; tone: NotificationTone; progress?: ProgressState; options?: NoticeOptions };
export type NoticeDisplayState = { type: NotificationType; phase: string; remainingMs: number | null; pauseReasons: string[]; revision: number };
export type NoticeHandle = { dismiss: () => void; inspect: () => NoticeDisplayState };
type ViewHandle = NoticeHandle & { dispose: () => void };
type ProgressOwner = { snapshot: UiConfigV2; view?: ViewHandle; resultPresented: boolean; dispose: () => void; removed: () => void };
const progressOwners = new Set<ProgressOwner>();
const captureConfig = (options?: NoticeOptions) => normalizeUiConfigV2(options?.previewConfig) ?? snapshotUiConfigV2();
function duration(config: UiConfigV2, type: NotificationType, reason?: NoticeOptions['manualReason']): number | null {
  const policy = config.notificationDisplay.types[type];
  return !(type === 'error' && reason === 'delivery-unconfirmed') && (policy.mode === 'timed' || policy.mode === 'timedHide') ? policy.durationMs : null;
}

export function createNotificationQueue(show: (notice: Notification, done: () => void) => void) {
  const pending: Notification[] = []; let active: Notification | null = null;
  function next() { if (active || !pending.length) return; active = pending.shift()!; let finished = false; show(active, () => { if (finished) return; finished = true; active = null; next(); }); }
  return { push(notice: Notification) { if (!notice.progress && ((active?.message === notice.message && active.tone === notice.tone) || pending.some(item => item.message === notice.message && item.tone === notice.tone))) return; pending.push(notice); next(); } };
}
export function createNotificationStack<T>(changed: (items: readonly T[]) => void) {
  let items: T[] = [];
  return {
    get items(): readonly T[] { return items; },
    add(item: T) { items = [item, ...items]; changed(items); },
    remove(item: T) { items = items.filter(value => value !== item); changed(items); },
    cycle() { if (items.length < 2) return; items = [...items.slice(1), items[0]!]; changed(items); },
  };
}
type Card = { notice: Notification; wrapper: HTMLDivElement; node: HTMLDivElement; body: HTMLDivElement; width: number;
  pause: () => void; resume: () => void; dismiss: () => void; reduce: () => void; dispose: () => void; settleEnter: () => void;
  restack: (index: number, ms: number) => void; inspect: () => NoticeDisplayState; stackMs: number; leaving: boolean };
const allCards = new Set<Card>();
const stack = createNotificationStack<Card>(items => items.forEach((card, index) => {
  card.wrapper.style.setProperty('--notice-stack', `${reducedMotion() ? 0 : items[0]!.stackMs}ms`);
  card.wrapper.style.setProperty('--stack-depth', String(Math.min(index, 3)));
  card.wrapper.style.setProperty('--capsule-width', `${Math.max(...items.map(item => item.width))}px`);
  card.wrapper.style.zIndex = String(100 - index);
  card.wrapper.classList.toggle('is-background', index > 0);
  card.wrapper.classList.toggle('is-deep', index > 3);
  card.wrapper.setAttribute('aria-label', `${index === 0 ? '当前' : '背景'}通知 ${index + 1}/${items.length}，按回车切换下一条`);
  card.wrapper.tabIndex = index > 3 ? -1 : 0;
  card.body.inert = index > 0;
  card.restack(index, reducedMotion() ? 0 : items[0]!.stackMs);
  if (index > 0) card.settleEnter();
}));
let portalObserver: MutationObserver | undefined;
let disposeEnvironment: (() => void) | undefined;
function reducedMotion(): boolean {
  return document.documentElement.dataset.motion === 'reduce' || document.documentElement.dataset.performance === 'low'
    || (typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches);
}
function ensureRegion(): HTMLElement | null {
  const region = document.getElementById('toast-region'); if (!region) return null;
  const dialogs = [...document.querySelectorAll<HTMLDialogElement>('dialog[open]')];
  const parent = dialogs.at(-1) ?? document.body;
  if (region.parentElement !== parent) {
    if ('showPopover' in region && region.matches(':popover-open')) region.hidePopover?.();
    parent.append(region);
  }
  if ('showPopover' in region) {
    region.setAttribute('popover', 'manual');
    if (!region.matches(':popover-open')) { try { region.showPopover(); } catch { } }
  }
  return region;
}
export function initializeNotifications(): void {
  if (disposeEnvironment || typeof document === 'undefined') return;
  const sync = () => {
    for (const card of allCards) {
      if (reducedMotion()) card.reduce();
      if (document.hidden || !document.hasFocus()) card.pause(); else card.resume();
    }
  };
  const media = matchMedia('(prefers-reduced-motion: reduce)');
  if (media.addEventListener) media.addEventListener('change', sync); else media.addListener?.(sync);
  document.addEventListener('visibilitychange', sync);
  window.addEventListener('focus', sync); window.addEventListener('blur', sync);
  if (typeof MutationObserver !== 'undefined') {
    portalObserver = new MutationObserver(() => { if (stack.items.length) ensureRegion(); });
    portalObserver.observe(document.body, { subtree: true, attributes: true, attributeFilter: ['open'] });
  }
  const preferences = typeof MutationObserver !== 'undefined' ? new MutationObserver(sync) : undefined;
  preferences?.observe(document.documentElement, { attributes: true, attributeFilter: ['data-motion', 'data-performance'] });
  disposeEnvironment = () => {
    if (media.removeEventListener) media.removeEventListener('change', sync); else media.removeListener?.(sync);
    preferences?.disconnect(); portalObserver?.disconnect(); portalObserver = undefined;
    document.removeEventListener('visibilitychange', sync); window.removeEventListener('focus', sync); window.removeEventListener('blur', sync);
  };
}
export function disposeNotifications(): void {
  for (const owner of [...progressOwners]) owner.dispose();
  for (const card of [...allCards]) card.dispose();
  disposeEnvironment?.(); disposeEnvironment = undefined;
}
function displayNotification(notice: Notification): ViewHandle | undefined {
  if (notice.progress?.canceled || notice.options?.signal?.aborted) return;
  const region = ensureRegion(); if (!region) return;
  initializeNotifications();
  const snapshot = notice.progress?.owner?.snapshot ?? captureConfig(notice.options);
  const wrapper = document.createElement('div'); wrapper.className = 'notification-stack-card'; wrapper.setAttribute('role', 'group');
  const node = document.createElement('div'); node.className = `notification-capsule notification-capsule--${notice.tone}`;
  const body = document.createElement('div'); body.className = 'notification-capsule__body';
  const dot = document.createElement('span'); dot.className = 'notification-capsule__dot'; dot.setAttribute('aria-hidden', 'true');
  const text = document.createElement('span'); text.className = 'notification-capsule__text'; text.textContent = notice.message;
  text.setAttribute('role', notice.tone === 'error' ? 'alert' : 'status'); text.setAttribute('aria-atomic', 'true');
  node.setAttribute('aria-busy', String(Boolean(notice.progress && !notice.progress.settled)));
  const close = document.createElement('button'); close.className = 'notification-capsule__close'; close.type = 'button'; close.setAttribute('aria-label', '关闭通知'); close.textContent = '×';
  body.append(dot, text);
  if (notice.options?.action) {
    const action = document.createElement('button'); action.type = 'button'; action.className = 'notification-capsule__action'; action.textContent = notice.options.action.label;
    action.addEventListener('click', async event => {
      event.stopPropagation(); if (action.disabled) return; action.disabled = true;
      actionBusy = true; resume();
      try { await notice.options!.action!.run(); dismiss(); }
      catch (error) { if (!leaving) notify(error instanceof Error ? error.message : '操作暂时未完成，请重试', 'error', { signal: notice.options?.signal, ...(notice.options?.previewConfig ? { previewConfig: snapshot } : {}) }); }
      finally { action.disabled = false; actionBusy = false; resume(); }
    }); body.append(action);
  }
  body.append(close); node.append(body); wrapper.append(node); region.append(wrapper);
  const width = Math.min(340, Math.max(notice.options?.action ? 310 : 250, Math.min(notice.message.length * 9, 260) + (notice.options?.action ? 95 : 55)));
  wrapper.style.setProperty('--capsule-width', `${width}px`); node.dataset.phase = 'enter';
  let leaving = false, disposed = false, contentBusy = false, actionBusy = false, hovered = false, stackBusy = false;
  let position = -1, appliedVersion = notice.progress?.settled ? notice.progress.version : -1;
  let currentTone: NotificationType = notice.progress && !notice.progress.settled ? 'loading' : notice.tone;
  if (notice.progress?.settled && notice.progress.owner) notice.progress.owner.resultPresented = true;
  const readTimer = createNotificationDisplayTimer(dismiss, notice.options?.clock);
  readTimer.setReasons(['enter', 'background']); readTimer.reset(duration(snapshot, currentTone, notice.options?.manualReason));
  if (currentTone === 'error' && notice.options?.manualReason === 'delivery-unconfirmed') node.dataset.manualReason = notice.options.manualReason;
  const jobs = new Map<string, PhaseJob>();
  const inspect = (): NoticeDisplayState => ({ type: currentTone, phase: disposed ? 'disposed' : node.dataset.phase ?? 'enter',
    remainingMs: readTimer.inspect().remainingMs, pauseReasons: readTimer.inspect().pauseReasons, revision: snapshot.revision });
  const card: Card = { notice, wrapper, node, body, width, pause, resume, dismiss, dispose, reduce, settleEnter, restack, inspect,
    stackMs: snapshot.notificationMotion.stackMs, leaving: false };
  function timeline() { return notificationTimeline(snapshot, currentTone, reducedMotion()); }
  function applyTiming() {
    const t = timeline();
    for (const [key, value] of Object.entries({ enter: t.enterMs, exit: t.exitMs, 'text-out': t.textOutMs, 'text-in': t.textInMs,
      'copy-delay': t.copyDelayMs, 'copy-in': t.copyInMs, 'copy-out': t.copyOutMs })) node.style.setProperty(`--notice-${key}`, `${value}ms`);
    node.dataset.motionType = currentTone; node.dataset.configRevision = String(snapshot.revision);
  }
  function phase(key: string, element: EventTarget, animation: string, ms: number, callback: () => void) {
    jobs.get(key)?.cancel();
    jobs.set(key, waitForNoticeAnimation(element, animation, ms, () => { jobs.delete(key); callback(); }));
  }
  function cancelJobs() { for (const job of jobs.values()) job.cancel(); jobs.clear(); }
  function settleEnter() { if (node.dataset.phase === 'enter') { jobs.get('enter')?.finish(); } }
  function reduce() {
    applyTiming(); wrapper.style.setProperty('--notice-stack', '0ms');
    for (const key of [...jobs.keys()]) jobs.get(key)?.finish();
  }
  function restack(index: number, ms: number) {
    const moved = position !== -1 && position !== index;
    position = index;
    if (moved) {
      jobs.get('stack')?.cancel(); stackBusy = ms > 0; resume();
      jobs.set('stack', waitForNoticeTransition(wrapper, ms, () => {
        jobs.delete('stack'); stackBusy = false; resume();
      }));
    }
    resume();
  }
  applyTiming();
  const resize = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(() => {
    if (stack.items[0] === card) region.style.setProperty('--stack-front-height', `${Math.max(56, node.offsetHeight)}px`);
  }) : undefined;
  resize?.observe(node);
  function dispose() {
    if (disposed) return; disposed = true;
    leaving = card.leaving = true; readTimer.dispose(); cancelJobs(); notice.progress?.listeners.delete(applyProgress);
    notice.options?.signal?.removeEventListener('abort', dispose);
    resize?.disconnect(); allCards.delete(card); stack.remove(card); wrapper.remove();
    notice.progress?.owner?.removed();
  }
  function dismiss() {
    if (leaving) return; leaving = card.leaving = true;
    readTimer.dispose(); cancelJobs(); notice.progress?.listeners.delete(applyProgress);
    resize?.disconnect();
    applyTiming();
    node.dataset.phase = 'exit'; node.classList.add('is-leaving'); wrapper.classList.add('is-exiting');
    wrapper.classList.remove('is-background', 'is-deep');
    const focused = wrapper.contains(document.activeElement);
    wrapper.inert = true;
    stack.remove(card);
    const dialog = wrapper.closest<HTMLDialogElement>('dialog[open]');
    const restore = dialog?.querySelector<HTMLElement>('input:not([disabled]),textarea:not([disabled])') ?? dialog?.querySelector<HTMLElement>('button:not([disabled])') ?? document.getElementById('main-content');
    if (focused) (stack.items[0]?.wrapper ?? restore)?.focus({ preventScroll: true });
    phase('exit', node, 'notification-drop-out', timeline().exitMs, dispose);
  }
  function pause() { resume(); }
  function resume() {
    readTimer.setReasons([
      ...(leaving ? ['leaving'] : []), ...(document.hidden ? ['hidden'] : []), ...(!document.hasFocus() ? ['blur'] : []),
      ...(stack.items[0] !== card ? ['background'] : []), ...(hovered || wrapper.matches(':hover') ? ['hover'] : []),
      ...(wrapper.contains(document.activeElement) ? ['focus'] : []), ...(node.dataset.phase === 'enter' ? ['enter'] : []),
      ...(contentBusy ? ['text'] : []), ...(stackBusy ? ['stack'] : []), ...(actionBusy ? ['action'] : []),
    ]);
  }
  function applyProgress() {
    if (notice.progress?.canceled) { dismiss(); return; }
    const progress = notice.progress;
    const content = progress?.message ?? progress?.updateMessage;
    if (!progress || !content || node.dataset.phase === 'enter' || contentBusy || progress.version === appliedVersion || leaving) return;
    contentBusy = true; appliedVersion = progress.version; pause();
    const completed = progress.settled;
    if (completed && progress.owner) progress.owner.resultPresented = true;
    currentTone = completed ? progress.tone ?? 'success' : 'loading'; applyTiming();
    node.dataset.phase = 'text-out'; node.classList.add('is-content-changing');
    phase('text-out', text, 'notification-word-out', timeline().textOutMs, () => {
      if (leaving) return;
      text.textContent = content;
      node.classList.remove('is-content-changing', ...['success', 'info', 'warning', 'error', 'loading'].map(tone => `notification-capsule--${tone}`));
      node.classList.add(`notification-capsule--${currentTone}`, 'is-content-arriving');
      text.setAttribute('role', currentTone === 'error' ? 'alert' : 'status'); node.setAttribute('aria-busy', String(!completed));
      node.dataset.phase = 'text-in';
      phase('text-in', text, 'notification-word-in', timeline().textInMs, () => {
        node.classList.remove('is-content-arriving'); node.dataset.phase = completed ? 'complete' : 'capsule';
        if (completed) readTimer.reset(duration(snapshot, currentTone, notice.options?.manualReason));
        contentBusy = false;
        applyProgress(); resume();
      });
    });
  }
  const cycle = () => { if (stack.items.length < 2) return; const focused = wrapper.contains(document.activeElement); stack.cycle(); if (focused) stack.items[0]?.wrapper.focus({ preventScroll: true }); };
  close.addEventListener('click', event => { event.stopPropagation(); dismiss(); });
  wrapper.addEventListener('click', event => { if (!(event.target as Element).closest('button,a,input')) cycle(); });
  wrapper.addEventListener('keydown', event => { if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); dismiss(); } else if (event.target === wrapper && ['Enter', ' '].includes(event.key)) { event.preventDefault(); cycle(); } });
  wrapper.addEventListener('mouseenter', () => { hovered = true; pause(); });
  wrapper.addEventListener('mouseleave', () => { hovered = false; resume(); });
  wrapper.addEventListener('focusin', pause); wrapper.addEventListener('focusout', () => queueMicrotask(resume));
  notice.progress?.listeners.add(applyProgress); notice.options?.signal?.addEventListener('abort', dispose, { once: true }); allCards.add(card);
  phase('enter', node, 'notification-drop-in', timeline().enterMs, () => {
    if (!leaving) { node.dataset.phase = notice.progress?.settled && notice.progress.owner?.resultPresented ? 'complete' : 'capsule'; applyProgress(); resume(); }
  });
  stack.add(card);
  return { dismiss, dispose, inspect };
}
export function notify(message: string, tone: NotificationTone = 'success', options?: NoticeOptions): NoticeHandle | undefined {
  if (typeof document === 'undefined' || !message || options?.signal?.aborted) return;
  const existing = !options?.previewConfig && stack.items.find(card => !card.notice.progress && !card.notice.options?.previewConfig && card.notice.message === message && card.notice.tone === tone && card.notice.options?.action?.run === options?.action?.run && card.notice.options?.manualReason === options?.manualReason && card.notice.options?.signal === options?.signal && card.notice.options?.clock === options?.clock);
  if (existing) return { dismiss: existing.dismiss, inspect: existing.inspect };
  return displayNotification({ message, tone, options });
}
export function beginProgressNotice(message = '正在检查连接…', options?: NoticeOptions) {
  const progress: ProgressState = { version: 0, settled: false, listeners: new Set() };
  let disposed = false, waitingPresented = false;
  const owner: ProgressOwner = { snapshot: captureConfig(options), resultPresented: false, dispose, removed };
  progress.owner = owner;
  function render() {
    if (disposed || owner.view || (progress.settled ? owner.resultPresented : waitingPresented) || typeof document === 'undefined') return;
    owner.view = displayNotification(progress.settled
      ? { message: progress.message!, tone: progress.tone ?? 'success', progress, options }
      : { message, tone: 'info', progress, options });
    if (owner.view && !progress.settled) waitingPresented = true;
  }
  function removed() {
    owner.view = undefined;
    if (disposed) return;
    if (progress.settled && owner.resultPresented) dispose();
    else if (progress.settled) render();
  }
  function dispose() {
    if (disposed) return; disposed = true; progress.canceled = true;
    options?.signal?.removeEventListener('abort', dispose); progress.listeners.clear(); progressOwners.delete(owner);
    owner.view?.dispose(); owner.view = undefined;
  }
  if (options?.signal?.aborted) dispose();
  else if (typeof document !== 'undefined') {
    progressOwners.add(owner); progress.listeners.add(render); options?.signal?.addEventListener('abort', dispose, { once: true }); render();
  }
  return {
    update(text: string) { if (disposed || progress.settled || !text) return; progress.updateMessage = text; progress.version++; progress.listeners.forEach(listener => listener()); },
    finish(text: string, tone: NotificationTone = 'success') { if (disposed || progress.settled) return; progress.settled = true;
      progress.message = text || '操作已完成'; progress.tone = tone; progress.version++; progress.listeners.forEach(listener => listener()); },
    cancel() { if (disposed) return; progress.canceled = true; progress.settled = true;
      const view = owner.view; dispose(); view?.dismiss(); },
    inspect: (): NoticeDisplayState => owner.view?.inspect() ?? { type: progress.settled ? progress.tone ?? 'success' : 'loading',
      phase: disposed ? 'disposed' : 'hidden', remainingMs: 0, pauseReasons: ['hidden-view'], revision: owner.snapshot.revision },
  };
}
