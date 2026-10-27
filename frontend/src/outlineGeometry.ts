export type OutlineInput = {
  clientWidth: number;
  clientHeight: number;
  border: { left: number; top: number; right: number; bottom: number };
  radius: number;
  stroke: number;
  clipped?: boolean;
};

export type OutlineGeometry = {
  viewWidth: number;
  viewHeight: number;
  left: number;
  top: number;
  extraWidth: number;
  extraHeight: number;
  rect: { x: number; y: number; width: number; height: number; rx: number };
};

export function computeOutline(input: OutlineInput): OutlineGeometry {
  const { stroke } = input;
  const border = input.clipped ? { left: 0, top: 0, right: 0, bottom: 0 } : input.border;
  const radius = input.clipped ? Math.max(0, input.radius - Math.max(input.border.left, input.border.top)) : input.radius;
  const half = stroke / 2;
  const viewWidth = Math.max(1, input.clientWidth + border.left + border.right);
  const viewHeight = Math.max(1, input.clientHeight + border.top + border.bottom);
  const rx = Math.max(0, Math.min(radius - half, (viewWidth - stroke) / 2, (viewHeight - stroke) / 2));
  return {
    viewWidth,
    viewHeight,
    left: 0 - border.left,
    top: 0 - border.top,
    extraWidth: border.left + border.right,
    extraHeight: border.top + border.bottom,
    rect: {
      x: half,
      y: half,
      width: Math.max(0, viewWidth - stroke),
      height: Math.max(0, viewHeight - stroke),
      rx,
    },
  };
}

const px = (value: string): number => Number.parseFloat(value) || 0;

export function applyOutline(
  svg: SVGSVGElement,
  shapes: SVGRectElement[],
  reference: HTMLElement,
  container: HTMLElement = reference,
  fallbackStroke = 1.2,
): void {
  const style = getComputedStyle(reference);
  const first = shapes[0];
  const measuredStroke = first ? px(getComputedStyle(first).strokeWidth) : 0;
  const clips = (value?: string): boolean => Boolean(value) && value !== "visible";
  const clipped = clips(style.overflowX) || clips(style.overflowY);
  const geometry = computeOutline({
    clipped,
    clientWidth: container.clientWidth,
    clientHeight: container.clientHeight,
    border: { left: px(style.borderLeftWidth), top: px(style.borderTopWidth), right: px(style.borderRightWidth), bottom: px(style.borderBottomWidth) },
    radius: px(style.borderTopLeftRadius),
    stroke: measuredStroke > 0 ? measuredStroke : fallbackStroke,
  });
  if (reference.dataset) reference.dataset.outlineBox = clipped ? "padding" : "border";
  svg.setAttribute("viewBox", `0 0 ${geometry.viewWidth} ${geometry.viewHeight}`);
  svg.style.left = `${geometry.left}px`;
  svg.style.top = `${geometry.top}px`;
  svg.style.right = "auto";
  svg.style.bottom = "auto";
  svg.style.width = `calc(100% + ${geometry.extraWidth}px)`;
  svg.style.height = `calc(100% + ${geometry.extraHeight}px)`;
  for (const shape of shapes) {
    shape.setAttribute("x", String(geometry.rect.x));
    shape.setAttribute("y", String(geometry.rect.y));
    shape.setAttribute("width", String(geometry.rect.width));
    shape.setAttribute("height", String(geometry.rect.height));
    shape.setAttribute("rx", String(geometry.rect.rx));
    shape.setAttribute("ry", String(geometry.rect.rx));
  }
}
