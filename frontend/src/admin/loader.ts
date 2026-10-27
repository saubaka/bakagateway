export const START_DELAY_MS = 140;
export const MIN_SHOW_MS = 360;
export const FADE_MS = 260;

export type LoaderTimers = {
  now(): number;
  set(callback: () => void, ms: number): number;
  clear(handle: number): void;
};

export const realTimers: LoaderTimers = {
  now: () => performance.now(),
  set: (callback, ms) => window.setTimeout(callback, ms),
  clear: (handle) => window.clearTimeout(handle),
};

let gateUntil = 0;
export const loaderGate = {
  delay(now = performance.now()): number { return Math.max(0, gateUntil - now); },
  reset(): void { gateUntil = 0; },
};

export type LoaderController = {
  setBusy(busy: boolean): void;
  dispose(): void;
};

export function createLoader(onChange: (visible: boolean) => void, timers: LoaderTimers = realTimers): LoaderController {
  let visible = false;
  let shownAt = 0;
  let startTimer = 0;
  let endTimer = 0;
  let busy = false;
  const show = (): void => {
    startTimer = 0;
    if (!busy || visible) return;
    visible = true; shownAt = timers.now();
    gateUntil = shownAt + 60_000;
    onChange(true);
  };
  const hide = (): void => {
    endTimer = 0;
    if (busy || !visible) return;
    visible = false;
    gateUntil = timers.now() + FADE_MS;
    onChange(false);
  };
  return {
    setBusy(next: boolean): void {
      if (next === busy) return;
      busy = next;
      if (busy) {
        if (endTimer) { timers.clear(endTimer); endTimer = 0; }
        if (visible) gateUntil = timers.now() + 60_000;
        else if (!startTimer) startTimer = timers.set(show, START_DELAY_MS);
        return;
      }
      if (startTimer) { timers.clear(startTimer); startTimer = 0; }
      if (!visible) return;
      const remaining = Math.max(0, MIN_SHOW_MS - (timers.now() - shownAt));
      gateUntil = timers.now() + remaining + FADE_MS;
      if (endTimer) timers.clear(endTimer);
      endTimer = timers.set(hide, remaining);
    },
    dispose(): void {
      if (startTimer) timers.clear(startTimer);
      if (endTimer) timers.clear(endTimer);
      startTimer = 0; endTimer = 0;
      gateUntil = 0;
    },
  };
}
