<template>
  <svg class="admin-icon" :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
    <component :is="shape[0]" v-for="(shape, index) in shapes[name]" :key="index" v-bind="shape[1]" />
  </svg>
</template>

<script setup lang="ts">
import type { IconName } from "../../admin/navModel";

withDefaults(defineProps<{ name: IconName; size?: number }>(), { size: 20 });

type Shape = ["path" | "rect" | "circle", Record<string, string | number>];
const p = (d: string, extra: Record<string, string | number> = {}): Shape => ["path", { d, ...extra }];
const rect = (x: number, y: number, width: number, height: number, rx: number): Shape => ["rect", { x, y, width, height, rx }];
const circle = (cx: number, cy: number, r: number): Shape => ["circle", { cx, cy, r }];

const shapes: Record<IconName, Shape[]> = {
  overview: [rect(3.5, 3.5, 7, 7, 1.8), rect(13.5, 3.5, 7, 7, 1.8), rect(3.5, 13.5, 7, 7, 1.8), rect(13.5, 13.5, 7, 7, 1.8)],
  accounts: [circle(9, 8, 3.4), p("M2.8 19.5c0-3.4 2.8-5.6 6.2-5.6s6.2 2.2 6.2 5.6"), p("M15.6 4.8a3.4 3.4 0 0 1 0 6.4M18 14.2c2 .6 3.2 2.4 3.2 5.3")],
  invites: [p("M3.5 9.2a2.3 2.3 0 0 0 0 5.6V18a1 1 0 0 0 1 1h15a1 1 0 0 0 1-1v-3.2a2.3 2.3 0 0 1 0-5.6V6a1 1 0 0 0-1-1h-15a1 1 0 0 0-1 1z"), p("M14.5 5v14", { "stroke-dasharray": "2 2.6" })],
  ops: [p("M3 12.5h4l2.6-7 4.6 13 2.6-6H21")],
  security: [p("M12 3.2 4.8 6v5.4c0 4.4 3 8.1 7.2 9.4 4.2-1.3 7.2-5 7.2-9.4V6z"), p("m9 12 2.2 2.2L15.2 10")],
  human: [circle(10, 8, 3.4), p("M3.2 19.6c0-3.4 3-5.6 6.8-5.6 1.2 0 2.4.2 3.4.7"), p("m15.6 17.8 2.1 2.1 4.1-4.5")],
  admins: [circle(12, 8, 3.6), p("M5 20c0-3.5 3.1-5.8 7-5.8s7 2.3 7 5.8")],
  system: [p("M4 7.5h9M17.5 7.5H20M4 16.5h2.5M11 16.5h9"), circle(15.2, 7.5, 2.2), circle(8.8, 16.5, 2.2)],
  seo: [circle(12, 12, 8.6), p("M3.4 12h17.2"), p("M12 3.4c2.3 2.4 3.5 5.2 3.5 8.6s-1.2 6.2-3.5 8.6c-2.3-2.4-3.5-5.2-3.5-8.6S9.7 5.8 12 3.4z")],
  logout: [p("M9.5 4.5H6a1.5 1.5 0 0 0-1.5 1.5v12A1.5 1.5 0 0 0 6 19.5h3.5"), p("m15.5 8 4 4-4 4M19.5 12h-10")],
  mail: [rect(3.5, 5.5, 17, 13, 2.2), p("m4.2 7.6 7.8 5.6 7.8-5.6")],
  search: [circle(11, 11, 6.5), p("m20 20-4.2-4.2")],
  panel: [rect(3.5, 4.5, 17, 15, 2.4), p("M9.5 4.5v15")],
  return: [p("M9 14 4.5 9.5 9 5"), p("M4.5 9.5H15a4.5 4.5 0 0 1 0 9h-3")],
  send: [p("M20.5 3.5 10.8 13.2"), p("M20.5 3.5 14 20.5l-3.2-7.3-7.3-3.2z")],
  alert: [circle(12, 12, 8.8), p("M12 7.6v5.4"), p("M12 16.6v.01")],
  clock: [circle(12, 12, 8.8), p("M12 7v5.2l3.3 2")],
  unread: [rect(3.5, 5.5, 17, 13, 2.2), p("m4.2 7.6 7.8 5.6 3.2-2.3"), circle(19, 6, 2.4)],
  chevron: [p("m9.5 5.5 6.5 6.5-6.5 6.5")],
};
</script>

<style scoped>
.admin-icon { display: block; flex: 0 0 auto; }
</style>
