import type { NotificationType, UiConfig } from './shared/notificationMotion.ts';

export function notificationTimeline(config: Pick<UiConfig, 'notificationMotion'>, type: NotificationType, reduced = false) {
  const timing = config.notificationMotion.types[type];
  const enterMs = reduced ? 0 : timing.enterMs, exitMs = reduced ? 0 : timing.exitMs;
  const copyDelayMs = Math.floor(enterMs * .8);
  return { enterMs, exitMs, textOutMs: reduced ? 0 : timing.textOutMs, textInMs: reduced ? 0 : timing.textInMs,
    stackMs: reduced ? 0 : config.notificationMotion.stackMs, copyDelayMs,
    copyInMs: enterMs - copyDelayMs, copyOutMs: Math.round(exitMs * .18) };
}

export function waitForNoticeTransition(element: EventTarget, duration: number, done: () => void): PhaseJob {
  let settled = false, timer: ReturnType<typeof setTimeout> | undefined;
  const cleanup = () => { clearTimeout(timer); element.removeEventListener('transitionend', ended); };
  const finish = () => { if (settled) return; settled = true; cleanup(); done(); };
  const ended = (event: Event) => { if (event.target === element && (event as TransitionEvent).propertyName === 'transform') finish(); };
  if (duration === 0) queueMicrotask(finish);
  else { element.addEventListener('transitionend', ended); timer = setTimeout(finish, duration + 48); }
  return { finish, cancel() { if (settled) return; settled = true; cleanup(); } };
}
export type PhaseJob = { finish: () => void; cancel: () => void };
export function waitForNoticeAnimation(element: EventTarget, name: string, duration: number, done: () => void): PhaseJob {
  let settled = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const cleanup = () => { clearTimeout(timer); element.removeEventListener('animationend', ended); };
  const finish = () => { if (settled) return; settled = true; cleanup(); done(); };
  const ended = (event: Event) => {
    if (event.target === element && (event as AnimationEvent).animationName === name) finish();
  };
  if (duration === 0) queueMicrotask(finish);
  else { element.addEventListener('animationend', ended); timer = setTimeout(finish, duration + 48); }
  return { finish, cancel() { if (settled) return; settled = true; cleanup(); } };
}
