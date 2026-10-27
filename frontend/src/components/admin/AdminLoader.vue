<template>
  <div class="admin-loader" :class="{ 'is-visible': visible }" aria-hidden="true">
    <div class="admin-loader__card">
      <svg class="admin-loader__art" viewBox="0 0 120 120" fill="none" stroke-linecap="round" stroke-linejoin="round" focusable="false">
        <circle class="admin-loader__ring" cx="60" cy="60" r="46" />
        <circle class="admin-loader__orbit" cx="60" cy="60" r="46" pathLength="100" />
        <g class="admin-loader__panes" transform="translate(60 60) scale(2.1) translate(-20 -20) rotate(-2 20 20)">
          <path class="admin-loader__pane" pathLength="1" d="M14.333 11.25H14.333A3.417 3.417 0 0 1 17.75 14.667V24.5A4.25 4.25 0 0 1 13.5 28.75H12.667A3.417 3.417 0 0 1 9.25 25.333V16.333A5.083 5.083 0 0 1 14.333 11.25Z" />
          <path class="admin-loader__pane is-second" pathLength="1" d="M25.667 11.25H25.667A5.083 5.083 0 0 1 30.75 16.333V25.333A3.417 3.417 0 0 1 27.333 28.75H26.5A4.25 4.25 0 0 1 22.25 24.5V14.667A3.417 3.417 0 0 1 25.667 11.25Z" transform="translate(0 2) rotate(3 26.5 20)" />
        </g>
        <g class="admin-loader__dots">
          <circle cx="60" cy="108" r="2" />
          <circle cx="68" cy="108" r="2" />
          <circle cx="52" cy="108" r="2" />
        </g>
      </svg>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue";
import { FADE_MS, createLoader } from "../../admin/loader.ts";

const props = defineProps<{ active: boolean }>();
const visible = ref(false);
const controller = createLoader((next) => { visible.value = next; });
watch(() => props.active, (busy) => controller.setBusy(busy), { immediate: true });
let restoreTimer = 0;
const root = typeof document === "undefined" ? null : document.documentElement;
watch(visible, (shown) => {
  window.clearTimeout(restoreTimer);
  if (shown) root?.setAttribute("data-route-loading", "");
  else restoreTimer = window.setTimeout(() => root?.removeAttribute("data-route-loading"), FADE_MS);
});
onBeforeUnmount(() => { window.clearTimeout(restoreTimer); root?.removeAttribute("data-route-loading"); controller.dispose(); });
</script>

<style scoped>
.admin-loader { position: fixed; z-index: 70; top: 0; bottom: 0; right: 0; left: var(--rail-w, 0px); display: grid; place-items: center; pointer-events: none; opacity: 0; visibility: hidden; transition: opacity 240ms var(--ease), visibility 0s linear 240ms, left 260ms var(--ease); }
.admin-loader.is-visible { opacity: 1; visibility: visible; transition: opacity 280ms var(--ease), visibility 0s, left 260ms var(--ease); }
.admin-loader__card { display: grid; place-items: center; width: 132px; height: 132px; border: 1px solid var(--line-blue); border-radius: 36px; background: rgba(255, 255, 255, .78); -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px); box-shadow: 0 10px 32px rgba(91, 130, 169, .1); transform: translate3d(0, 6px, 0) scale(.94); transition: transform 420ms var(--spring); }
.admin-loader.is-visible .admin-loader__card { transform: none; }
.admin-loader__art { width: 108px; height: 108px; overflow: visible; }
.admin-loader__ring { stroke: var(--line-blue); stroke-width: 1.5; }
.admin-loader__orbit { stroke: var(--line-blue-strong); stroke-width: 2.4; stroke-dasharray: 22 78; transform-origin: 60px 60px; animation: loader-orbit 1.7s linear infinite; }
.admin-loader__pane { stroke: var(--blue-300, #a8d0f4); stroke-width: .9; stroke-dasharray: 1; animation: loader-draw 2.6s cubic-bezier(.45, .05, .25, 1) infinite; }
.admin-loader__pane.is-second { animation-delay: .32s; }
.admin-loader__dots circle { fill: var(--line-blue-strong); animation: loader-dot 1.3s ease-in-out infinite; }
.admin-loader__dots circle:nth-child(2) { animation-delay: .18s; }
.admin-loader__dots circle:nth-child(3) { animation-delay: .36s; }
@keyframes loader-orbit { to { transform: rotate(360deg); } }
@keyframes loader-draw { 0% { stroke-dashoffset: 1; opacity: .35; } 42% { stroke-dashoffset: 0; opacity: 1; } 70% { stroke-dashoffset: 0; opacity: 1; } 100% { stroke-dashoffset: -1; opacity: .35; } }
@keyframes loader-dot { 0%, 100% { opacity: .25; transform: translateY(0); } 50% { opacity: 1; transform: translateY(-3px); } }
@media (max-width: 900px) { .admin-loader { left: 0; } }
@media (prefers-reduced-motion: reduce) {
  .admin-loader, .admin-loader.is-visible, .admin-loader__card { transition: opacity 120ms linear; }
  .admin-loader__orbit, .admin-loader__pane, .admin-loader__dots circle { animation: none; }
  .admin-loader__pane { stroke-dashoffset: 0; }
}
</style>
