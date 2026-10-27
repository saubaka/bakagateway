import type { ObjectDirective } from "vue";

export const pressFrames: Keyframe[] = [
  { transform: "scale(1)" },
  { transform: "scale(.965)", offset: .28 },
  { transform: "scale(1.015)", offset: .7 },
  { transform: "scale(1)" },
];
export const submitPressFrames: Keyframe[] = [
  { transform: "translate3d(0,0,0) scale(1)" },
  { transform: "translate3d(0,1px,0) scale(.978)", offset: .22 },
  { transform: "translate3d(0,-1px,0) scale(1.008)", offset: .65 },
  { transform: "translate3d(0,0,0) scale(1)" },
];
export function allowsPressMotion(root: DOMStringMap, systemReduced: boolean): boolean {
  return root.motion !== "reduce" && root.performance !== "low" && !systemReduced;
}
const bindings = new WeakMap<HTMLElement, { click: () => void; animation?: Animation; timer?: ReturnType<typeof setTimeout> }>();
export const pressFeedbackDirective: ObjectDirective<HTMLElement, "submit" | undefined> = {
  mounted(el, options) {
    const submit = options?.value === "submit";
    const binding = {
      animation: undefined as Animation | undefined,
      timer: undefined as ReturnType<typeof setTimeout> | undefined,
      click() {
        if (!allowsPressMotion(document.documentElement.dataset, matchMedia("(prefers-reduced-motion: reduce)").matches)) return;
        binding.animation?.cancel();
        if (submit) {
          clearTimeout(binding.timer);
          el.classList.add("is-action-pressing");
          binding.timer = setTimeout(() => el.classList.remove("is-action-pressing"), 300);
        }
        binding.animation = el.animate(submit ? submitPressFrames : pressFrames, { duration: submit ? 240 : 360, easing: "cubic-bezier(.2,.8,.25,1)" });
      },
    };
    el.addEventListener("click", binding.click);
    bindings.set(el, binding);
  },
  beforeUnmount(el) {
    const binding = bindings.get(el);
    if (binding) { el.removeEventListener("click", binding.click); binding.animation?.cancel(); clearTimeout(binding.timer); if (binding.timer) el.classList.remove("is-action-pressing"); }
    bindings.delete(el);
  },
};
