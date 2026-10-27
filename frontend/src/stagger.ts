export type Stagger = { next(now: number): number; reset(): void };

export const STAGGER_STEP_MS = 70;
export const STAGGER_MAX_STEPS = 7;
export const STAGGER_WINDOW_MS = 180;

export function createStagger(step = STAGGER_STEP_MS, maxSteps = STAGGER_MAX_STEPS, windowMs = STAGGER_WINDOW_MS): Stagger {
  let count = 0;
  let last = Number.NEGATIVE_INFINITY;
  return {
    next(now: number): number {
      if (now - last > windowMs) count = 0;
      last = now;
      const delay = Math.min(count, maxSteps) * step;
      count += 1;
      return delay;
    },
    reset(): void { count = 0; last = Number.NEGATIVE_INFINITY; },
  };
}

export const stagger = createStagger();
