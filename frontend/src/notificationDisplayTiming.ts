export type NotificationDisplayClock = {
  now: () => number;
  setTimeout: (callback: () => void, ms: number) => unknown;
  clearTimeout: (token: unknown) => void;
};
const browserClock: NotificationDisplayClock = {
  now: () => performance.now(),
  setTimeout: (callback, ms) => setTimeout(callback, ms),
  clearTimeout: token => clearTimeout(token as ReturnType<typeof setTimeout>),
};

export function createNotificationDisplayTimer(expire: () => void, clock: NotificationDisplayClock = browserClock) {
  let remaining: number | null = null, started: number | null = null, token: unknown;
  let armed = false, disposed = false, expired = false, generation = 0;
  let reasons = new Set<string>();
  function stop() {
    generation++;
    if (started !== null && remaining !== null) remaining = Math.max(0, remaining - Math.max(0, clock.now() - started));
    started = null;
    if (armed) clock.clearTimeout(token);
    armed = false;
  }
  function arm() {
    if (disposed || expired || remaining === null || reasons.size) return;
    started = clock.now(); armed = true;
    const version = ++generation;
    token = clock.setTimeout(() => {
      if (disposed || expired || version !== generation) return;
      armed = false; started = null; remaining = 0; expired = true;
      if (!disposed) expire();
    }, remaining);
  }
  return {
    reset(durationMs: number | null) { if (disposed) return; stop(); remaining = durationMs; expired = false; arm(); },
    setReasons(next: Iterable<string>) {
      if (disposed) return;
      const updated = new Set(next);
      if (updated.size === reasons.size && [...updated].every(reason => reasons.has(reason))) return;
      stop(); reasons = updated; arm();
    },
    inspect() {
      return { remainingMs: remaining === null ? null : Math.max(0, remaining - (started === null ? 0 : Math.max(0, clock.now() - started))),
        pauseReasons: [...reasons], running: started !== null, expired, disposed };
    },
    dispose() { if (disposed) return; stop(); disposed = true; reasons.clear(); },
  };
}
