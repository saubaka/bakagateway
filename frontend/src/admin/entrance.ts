import type { Directive } from "vue";
import { stagger } from "../stagger.ts";
import { playCardParts } from "../cardParts.ts";
import { loaderGate } from "./loader.ts";

export const CARD_SELECTOR = ".admin-panel, .managed-page-card, .baka-overview-stat, .invite-reveal-card, .stat-card";

export const BLOCK_SELECTOR = [
  "form.form-grid", ".admin-filter-bar", ".invite-overview", ".admin-status-list", ".hv-section", ".hv-chart",
  "pre.log-block", ".seo-score", ".seo-group", ".seo-preview", ".seo-files", ".seo-switches", ".seo-code",
  ".mail-notice", ".mail-empty", ".admin-page-state", ".field-error", ".form-error", ".hint-line", ".hv-warn", ".hv-inline",
  ".baka-overview__error", ".seo-savebar", ".admin-users-table-scroll", ".table-scroll", ".permission-list",
].join(", ");

export const ROW_SELECTOR = [
  "tbody tr", ".check-row", ".hv-routes li", ".seo-check", ".admin-status-list > div", ".baka-overview__system-items > div",
  ".baka-overview__quick-actions > a", ".permission-list > .badge", ".seo-switches li",
].join(", ");

export const ENTRANCE_SELECTOR = `${CARD_SELECTOR}, ${BLOCK_SELECTOR}, ${ROW_SELECTOR}`;

export const MAX_ROWS_PER_BATCH = 40;

export const STAT_SELECTOR = ".baka-overview-stat";
export const STAT_STEP_MS = 120;
export function statDelay(base: number, index: number): number {
  return base + index * STAT_STEP_MS;
}

export type EntranceKind = "card" | "block" | "row";
export type EntranceSpec = { duration: number; distance: number; opacityOnly: boolean };

export function specFor(kind: EntranceKind, tag: string): EntranceSpec {
  if (tag === "TR") return { duration: 360, distance: 0, opacityOnly: true };
  if (kind === "card") return { duration: 520, distance: 14, opacityOnly: false };
  if (kind === "row") return { duration: 360, distance: 6, opacityOnly: false };
  return { duration: 420, distance: 8, opacityOnly: false };
}

export function dropNested<T>(items: T[], contains: (outer: T, inner: T) => boolean): T[] {
  return items.filter((item) => !items.some((other) => other !== item && contains(other, item)));
}

export function kindOf(element: Element): EntranceKind {
  if (element.matches(CARD_SELECTOR)) return "card";
  if (element.matches(ROW_SELECTOR)) return "row";
  return "block";
}

function reducedMotion(): boolean {
  const root = document.documentElement;
  return root.dataset.motion === "reduce" || root.dataset.performance === "low"
    || window.matchMedia("(prefers-reduced-motion: reduce)").matches || !("animate" in Element.prototype);
}

function visible(element: HTMLElement): boolean {
  return element.getClientRects().length > 0 && !element.closest("[data-enter='skip'], dialog, .admin-rail");
}

function play(element: HTMLElement, spec: EntranceSpec, delay: number): void {
  const from: Keyframe = spec.opacityOnly ? { opacity: 0 } : { opacity: 0, transform: `translate3d(0, ${spec.distance}px, 0)` };
  const to: Keyframe = spec.opacityOnly ? { opacity: 1 } : { opacity: 1, transform: "none" };
  element.animate([from, to], { duration: spec.duration, delay, easing: "cubic-bezier(.2,.8,.2,1)", fill: "backwards" });
}

function scheduleMotionTarget(element: HTMLElement, now: number, delay: number): void {
  element.dataset.motionAssignedAt = String(now);
  element.dataset.motionSlotDelay = String(delay);
}

function playStat(element: HTMLElement, delay: number): void {
  play(element, { duration: 560, distance: 18, opacityOnly: false }, delay);
  playCardParts(element, delay);
}

export function handleAdded(roots: Element[], now = performance.now()): number {
  if (reducedMotion()) return 0;
  const found = new Set<HTMLElement>();
  for (const root of roots) {
    if (!root.isConnected) continue;
    if (root.matches(ENTRANCE_SELECTOR)) found.add(root as HTMLElement);
    for (const element of root.querySelectorAll<HTMLElement>(ENTRANCE_SELECTOR)) found.add(element);
  }
  const ordered = [...found].filter((element) => !element.dataset.entered && visible(element))
    .sort((a, b) => (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1));
  const top = dropNested(ordered, (outer, inner) => outer.contains(inner));
  let rows = 0;
  let count = 0;
  let statBase = -1;
  let statIndex = 0;
  let floor = -1;
  let after = 0;
  const slot = (): number => (floor < 0 ? stagger.next(now) : floor + Math.min(after++, 4) * 70);
  const gate = loaderGate.delay(now);
  for (const element of top) {
    const kind = kindOf(element);
    if (kind === "row" && ++rows > MAX_ROWS_PER_BATCH) continue;
    element.dataset.entered = "1";
    count += 1;
    if (element.matches(STAT_SELECTOR)) {
      if (statBase < 0) statBase = stagger.next(now);
      const delay = statDelay(statBase, statIndex++);
      playStat(element, delay + gate);
      floor = delay + 90; after = 0;
      continue;
    }
    if (element.classList.contains("motion-line-target")) { scheduleMotionTarget(element, now, slot()); continue; }
    const cardDelay = slot() + gate;
    play(element, specFor(kind, element.tagName), cardDelay);
    if (kind !== "card") continue;
    playCardParts(element, cardDelay);
  }
  return count;
}

export function attachEntrance(root: HTMLElement): () => void {
  handleAdded([root]);
  if (typeof MutationObserver === "undefined") return () => {};
  const observer = new MutationObserver((records) => {
    const added: Element[] = [];
    for (const record of records) for (const node of record.addedNodes) if (node instanceof Element) added.push(node);
    if (added.length) handleAdded(added);
  });
  observer.observe(root, { childList: true, subtree: true });
  return () => observer.disconnect();
}

const disposers = new WeakMap<HTMLElement, () => void>();
export const adminEntranceDirective: Directive<HTMLElement> = {
  mounted(element) { disposers.set(element, attachEntrance(element)); },
  unmounted(element) { disposers.get(element)?.(); disposers.delete(element); },
};
