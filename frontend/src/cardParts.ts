export const PARTS_START_MS = 110;
export const PARTS_STEP_MS = 70;
export const PARTS_MAX_STEPS = 8;
export const PARTS_MAX_COUNT = 24;
export const PART_DURATION_MS = 420;

const UNIT_TAGS = new Set([
  "H1", "H2", "H3", "H4", "H5", "H6", "P", "SMALL", "STRONG", "EM", "LABEL", "BUTTON", "A", "UL", "OL", "DL", "TABLE", "PRE",
  "SVG", "IMG", "INPUT", "SELECT", "TEXTAREA", "CANVAS", "FIGURE", "BLOCKQUOTE", "CODE", "TIME",
]);
const UNIT_CLASS = /(^|[\s_-])(icon|logo|avatar|badge|pill|chip|status|tag|button|table-scroll|toggle|switch|seo-preview|hv-chart|range-tabs|field|check-row|permission-list|log-block|eyebrow)([\s_-]|$)/;
const SKIP_CLASS = /(^|\s)(motion-outline|motion-line-target|admin-panel|managed-page-card|baka-overview-stat|login-card|auth-card)(\s|$)/;

export type PartNode = {
  tagName: string;
  className?: unknown;
  children: ArrayLike<PartNode>;
  childNodes: ArrayLike<{ nodeType: number; textContent: string | null }>;
  hidden?: boolean;
};

function classText(node: PartNode): string {
  const value = node.className as unknown;
  if (typeof value === "string") return value;
  if (value && typeof (value as { baseVal?: unknown }).baseVal === "string") return (value as { baseVal: string }).baseVal;
  return "";
}

function hasOwnText(node: PartNode): boolean {
  for (let i = 0; i < node.childNodes.length; i += 1) {
    const child = node.childNodes[i]!;
    if (child.nodeType === 3 && (child.textContent ?? "").trim() !== "") return true;
  }
  return false;
}

function isUnit(node: PartNode): boolean {
  if (UNIT_TAGS.has(node.tagName.toUpperCase())) return true;
  if (UNIT_CLASS.test(classText(node))) return true;
  return node.children.length === 0 || hasOwnText(node);
}

export function collectCardParts<T extends PartNode>(card: T, isShown: (node: T) => boolean = () => true, max = PARTS_MAX_COUNT): T[] {
  const parts: T[] = [];
  const visit = (node: T): void => {
    for (let i = 0; i < node.children.length && parts.length < max; i += 1) {
      const child = node.children[i] as T;
      if (child.hidden || SKIP_CLASS.test(classText(child)) || child.tagName.toUpperCase() === "DIALOG") continue;
      if (!isShown(child)) continue;
      if (isUnit(child)) parts.push(child);
      else visit(child);
    }
  };
  visit(card);
  return parts;
}

export function partOffset(index: number): number {
  return PARTS_START_MS + Math.min(index, PARTS_MAX_STEPS) * PARTS_STEP_MS;
}

function isRendered(element: HTMLElement): boolean {
  return element.getClientRects().length > 0;
}

export function playCardParts(card: HTMLElement, baseDelay = 0): number {
  if (card.closest("[data-card-parts='off'], .mail-pane")) return 0;
  const parts = collectCardParts(card, isRendered);
  parts.forEach((part, index) => {
    part.dataset.entered = "1";
    const scale = /(^|[\s_-])(icon|logo|avatar)([\s_-]|$)/.test(classText(part));
    const from: Keyframe = scale ? { opacity: 0, transform: "translate3d(0, 6px, 0) scale(.72)" } : { opacity: 0, transform: "translate3d(0, 8px, 0)" };
    part.animate([from, { opacity: 1, transform: "none" }], {
      duration: PART_DURATION_MS, delay: baseDelay + partOffset(index), easing: "cubic-bezier(.2,.8,.2,1)", fill: "backwards",
    });
  });
  return parts.length;
}
