import type { Directive, DirectiveBinding } from "vue";
import { applyOutline } from "./outlineGeometry.ts";
import { stagger } from "./stagger.ts";
import { playCardParts } from "./cardParts.ts";
import { loaderGate } from "./admin/loader.ts";

type MotionKind = "feature" | "compact" | "control";
type MotionOptions = {
  kind?: MotionKind;
  delay?: number;
  reversible?: boolean;
};

type MotionRecord = {
  observer: IntersectionObserver | null;
  resizeObserver: ResizeObserver | null;
  animations: Animation[];
  duration: number;
  delayTimer: number;
  disabled: boolean;
  version: number;
  startedAt: number;
};

const records = new WeakMap<HTMLElement, MotionRecord>();
const mountedElements = new Set<HTMLElement>();
const SVG_NS = "http://www.w3.org/2000/svg";
let preferencesInitialized = false;

export type MotionPreference = "system" | "reduce";
export type PerformancePreference = "normal" | "low";

export function currentMotionPreferences(): {
  motion: MotionPreference;
  performance: PerformancePreference;
} {
  return {
    motion: document.documentElement.dataset.motion === "reduce" ? "reduce" : "system",
    performance: document.documentElement.dataset.performance === "low" ? "low" : "normal",
  };
}

function reducedMotion(): boolean {
  return (
    document.documentElement.dataset.motion === "reduce" ||
    document.documentElement.dataset.performance === "low" ||
    window.matchMedia("(prefers-reduced-motion: reduce)").matches ||
    !("animate" in Element.prototype)
  );
}

function settleInstantly(element: HTMLElement): void {
  const record = records.get(element);
  if (record) {
    window.clearTimeout(record.delayTimer);
    record.version += 1;
    record.disabled = true;
    for (const animation of record.animations) animation.cancel();
  }
  element.classList.remove("is-motion-active");
  element.classList.add("is-revealed");
  element.dataset.motionState = "settled";
}

function resumeMotion(element: HTMLElement): void {
  const record = records.get(element);
  if (!record?.disabled) return;
  record.disabled = false;
  for (const animation of record.animations) animation.cancel();
}

function releaseEffects(record: MotionRecord): void {
  for (const animation of record.animations) animation.cancel();
}

function prepare(record: MotionRecord, forward: boolean): void {
  for (const animation of record.animations) {
    animation.playbackRate = forward ? 1 : -1;
    if (!forward && animation.playState === "idle") animation.currentTime = record.duration;
    if (forward && animation.playState === "idle") animation.currentTime = 0;
  }
}

function syncMountedMotion(): void {
  for (const element of mountedElements) {
    if (reducedMotion()) settleInstantly(element);
    else resumeMotion(element);
  }
}

export function applyMotionPreferences(
  motion: MotionPreference,
  performance: PerformancePreference,
  persist = true,
): void {
  const root = document.documentElement;
  root.dataset.motion = motion;
  root.dataset.performance = performance;
  if (persist) {
    try {
      localStorage.setItem("bakagateway-motion", motion);
      localStorage.setItem("bakagateway-performance", performance);
    } catch {
    }
  }
  syncMountedMotion();
}

function optionsOf(binding: DirectiveBinding<MotionOptions | MotionKind | undefined>): Required<MotionOptions> {
  if (typeof binding.value === "string") {
    return { kind: binding.value, delay: 0, reversible: true };
  }
  return {
    kind: binding.value?.kind ?? "compact",
    delay: Math.max(0, Math.min(1200, binding.value?.delay ?? 0)),
    reversible: binding.value?.reversible ?? true,
  };
}

function createOutline(element: HTMLElement): { outline: SVGSVGElement; path: SVGRectElement } {
  const outline = document.createElementNS(SVG_NS, "svg");
  outline.classList.add("motion-outline");
  outline.setAttribute("aria-hidden", "true");
  outline.setAttribute("focusable", "false");
  outline.setAttribute("preserveAspectRatio", "none");

  const path = document.createElementNS(SVG_NS, "rect");
  path.classList.add("motion-outline__path");
  path.setAttribute("vector-effect", "non-scaling-stroke");
  path.setAttribute("pathLength", "1");
  path.style.setProperty("--motion-path-length", "1");
  outline.append(path);
  element.prepend(outline);
  return { outline, path };
}

function configureGeometry(element: HTMLElement, outline: SVGSVGElement, path: SVGRectElement): void {
  applyOutline(outline, [path], element, element, 1);
}

function entranceDelay(element: HTMLElement): number {
  const own = Number(element.dataset.motionDelay ?? 0);
  const now = performance.now();
  const assignedAt = Number(element.dataset.motionAssignedAt ?? 0);
  const gate = loaderGate.delay(now);
  if (assignedAt > 0) return own + gate + (now - assignedAt < 1500 ? Number(element.dataset.motionSlotDelay ?? 0) : 0);
  return own + gate + stagger.next(now);
}

function play(record: MotionRecord, forward: boolean, element: HTMLElement): void {
  if (record.disabled) return;
  if (reducedMotion()) {
    settleInstantly(element);
    return;
  }
  window.clearTimeout(record.delayTimer);
  const version = ++record.version;
  const run = (): void => {
    if (record.disabled || record.version !== version) return;
    if (reducedMotion()) {
      settleInstantly(element);
      return;
    }
    element.classList.add("is-motion-active");
    element.dataset.motionState = forward ? "drawing" : "reversing";
    record.startedAt = performance.now();
    prepare(record, forward);
    for (const animation of record.animations) animation.play();
    if (forward && element.dataset.motionKind !== "control") playCardParts(element, 0);
    const anchor = record.animations[0];
    anchor.finished
      .then(() => {
        if (record.disabled || record.version !== version) return;
        element.classList.remove("is-motion-active");
        element.classList.toggle("is-revealed", forward);
        element.dataset.motionState = forward ? "settled" : "idle";
        if (forward) releaseEffects(record);
      })
      .catch(() => undefined);
  };
  record.delayTimer = window.setTimeout(run, forward ? entranceDelay(element) : 0);
}

export function settleStalledMotion(now = performance.now()): number {
  let settled = 0;
  for (const element of mountedElements) {
    const state = element.dataset.motionState;
    if (state !== "drawing" && state !== "reversing") continue;
    const record = records.get(element);
    if (!record || record.disabled || now - record.startedAt < record.duration + 400) continue;
    for (const animation of record.animations) {
      try { animation.finish(); } catch { }
    }
    settled += 1;
  }
  return settled;
}

export function initializeMotionPreferences(): void {
  const root = document.documentElement;
  let savedMotion: MotionPreference = "system";
  let savedPerformance: PerformancePreference = "normal";
  try {
    savedMotion = localStorage.getItem("bakagateway-motion") === "reduce" ? "reduce" : "system";
    savedPerformance = localStorage.getItem("bakagateway-performance") === "low" ? "low" : "normal";
  } catch {
  }
  applyMotionPreferences(savedMotion, savedPerformance, false);
  root.dataset.componentMotionStyle = "soft";
  root.dataset.componentMotionSoftness = "light";
  root.dataset.componentMotionDuration = "620";
  root.classList.remove("motion-preparing");
  root.classList.add("is-motion-ready");
  if (!preferencesInitialized) {
    preferencesInitialized = true;
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onSystemMotionChange = (): void => syncMountedMotion();
    document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") settleStalledMotion(); });
    window.addEventListener("focus", () => { settleStalledMotion(); });
    if (typeof media.addEventListener === "function") media.addEventListener("change", onSystemMotionChange);
    else media.addListener(onSystemMotionChange);
  }
}

export const motionDirective: Directive<HTMLElement, MotionOptions | MotionKind | undefined> = {
  mounted(element, binding) {
    const options = optionsOf(binding);
    mountedElements.add(element);
    element.classList.add("motion-line-target");
    element.dataset.motionKind = options.kind;
    element.dataset.motionState = "idle";
    element.dataset.motionDelay = String(options.delay);
    element.dataset.motionOutline = "true";

    const { outline, path } = createOutline(element);
    configureGeometry(element, outline, path);
    element.classList.add("is-outline-ready");

    const duration = options.kind === "feature" ? 620 : options.kind === "control" ? 360 : 500;
    const timing: KeyframeAnimationOptions = {
      duration,
      easing: "cubic-bezier(.2,.78,.22,1)",
      fill: "both",
    };
    const animations = [
      path.animate([{ strokeDashoffset: 1 }, { strokeDashoffset: 0 }], timing),
      outline.animate(
        [
          { opacity: 0.2, filter: "blur(.7px)", transform: "scale(.988)" },
          { opacity: 1, filter: "none", transform: "none" },
        ],
        timing,
      ),
      element.animate(
        [
          { opacity: 0, transform: "translate3d(0, 8px, 0) scale(.992)" },
          { opacity: 1, transform: "none" },
        ],
        timing,
      ),
    ];
    for (const animation of animations) {
      animation.pause();
      animation.currentTime = 0;
    }

    const record: MotionRecord = {
      observer: null,
      resizeObserver: null,
      animations,
      duration,
      delayTimer: 0,
      disabled: false,
      version: 0,
      startedAt: 0,
    };
    records.set(element, record);

    if ("ResizeObserver" in window) {
      record.resizeObserver = new ResizeObserver(() => configureGeometry(element, outline, path));
      record.resizeObserver.observe(element);
    }

    if ("IntersectionObserver" in window) {
      record.observer = new IntersectionObserver(
        ([entry]) => {
          if (entry.isIntersecting) play(record, true, element);
          else if (options.reversible && element.dataset.motionState !== "idle") play(record, false, element);
        },
        { threshold: 0.08, rootMargin: "0px 0px -6%" },
      );
      record.observer.observe(element);
    } else {
      play(record, true, element);
    }
    if (reducedMotion()) settleInstantly(element);
  },
  unmounted(element) {
    mountedElements.delete(element);
    const record = records.get(element);
    if (!record) return;
    window.clearTimeout(record.delayTimer);
    record.version += 1;
    record.observer?.disconnect();
    record.resizeObserver?.disconnect();
    for (const animation of record.animations) animation.cancel();
    records.delete(element);
  },
};
