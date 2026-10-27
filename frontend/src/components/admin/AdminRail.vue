<template>
  <aside
    id="admin-sidebar"
    ref="root"
    class="admin-rail"
    :class="{
      'is-open': open,
      'is-collapsed': collapsed,
      'is-compact': compact,
    }"
    :aria-label="`${navigationLabel}导航`"
    :inert="compact && !open"
    @keydown="onKeydown"
  >
    <div class="admin-rail__head">
      <router-link
        class="admin-rail__brand"
        :to="{ name: homeRouteName }"
        :title="`${siteInfo.siteName} ${brandLabel}`"
        :aria-label="`${siteInfo.siteName} ${brandLabel}首页`"
        @click="emit('navigate')"
      >
        <span class="brand-mark"
          ><span class="window-symbol" aria-hidden="true"><i></i><i></i></span
        ></span>
        <span class="admin-rail__text">{{ siteInfo.siteName }}</span>
      </router-link>
      <button
        v-if="!compact"
        class="admin-rail__tool"
        type="button"
        :aria-pressed="collapsed ? 'true' : 'false'"
        :aria-label="collapsed ? '展开侧栏' : '收起侧栏'"
        :title="collapsed ? '展开侧栏' : '收起侧栏'"
        @click="emit('toggle-collapse')"
      >
        <AdminIcon name="panel" :size="18" />
      </button>
    </div>

    <button
      v-if="showSearch"
      class="admin-rail__search"
      type="button"
      aria-keyshortcuts="Control+K Meta+K"
      :title="`跳转到页面（${modifier} K）`"
      :aria-label="`跳转到… ${modifier} K`"
      @click="emit('palette')"
    >
      <AdminIcon name="search" :size="18" />
      <span class="admin-rail__text">跳转到…</span>
      <kbd class="admin-rail__text">{{ modifier }} K</kbd>
    </button>

    <nav ref="navElement" class="admin-rail__nav" :aria-label="navigationLabel">
      <span
        class="admin-rail__indicator"
        :class="{ 'is-ready': indicator.ready }"
        :style="indicatorStyle"
        aria-hidden="true"
      ></span>
      <section
        v-for="section in sections"
        :key="section.key"
        class="admin-rail__section"
      >
        <h2 v-if="section.label" class="admin-rail__label">
          <span class="admin-rail__text">{{ section.label }}</span>
        </h2>
        <ul>
          <li
            v-for="item in section.items"
            :key="item.name"
            :style="{ '--i': order.get(item.name) }"
          >
            <router-link
              class="admin-rail__link"
              :class="{ 'is-current': active === item.name }"
              :to="{ name: item.name }"
              :title="
                collapsed
                  ? `${item.label}（g ${item.shortcut}）`
                  : `g ${item.shortcut}`
              "
              :aria-keyshortcuts="`g ${item.shortcut}`"
              @click="emit('navigate')"
            >
              <AdminIcon :name="item.icon" />
              <span class="admin-rail__text">{{ item.label }}</span>
              <span
                v-if="count(item.badge)"
                class="admin-rail__badge"
                :class="item.badge === 'security' ? 'is-alert' : 'is-info'"
              >
                {{ count(item.badge)
                }}<span class="admin-rail__sr"> 项待处理</span>
              </span>
            </router-link>
          </li>
        </ul>
      </section>
    </nav>

    <div class="admin-rail__profile">
      <span class="avatar avatar--small" aria-hidden="true">{{ initial }}</span>
      <span
        class="admin-rail__who admin-rail__text"
        :title="`${username}（${roleLabel}）`"
        ><strong>{{ username }}</strong
        ><small>{{ roleLabel }}</small></span
      >
      <span class="admin-rail__tools">
        <router-link
          v-if="showReturn"
          class="admin-rail__tool"
          to="/login"
          title="返回登录"
          aria-label="返回登录"
          @click="emit('navigate')"
        >
          <AdminIcon name="return" :size="18" />
        </router-link>
        <button
          class="admin-rail__tool"
          type="button"
          :disabled="logoutBusy"
          :aria-label="logoutBusy ? '正在处理' : logoutLabel"
          :title="logoutLabel"
          @click="emit('logout')"
        >
          <AdminIcon name="logout" :size="18" />
        </button>
      </span>
    </div>
  </aside>
</template>

<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from "vue";
import AdminIcon from "./AdminIcon.vue";
import { siteInfo } from "../../siteInfo";
import type { RailBadgeKey, RailSection } from "../../admin/navModel";

const props = withDefaults(
  defineProps<{
    sections: RailSection[];
    current: string;
    pending?: string;
    badges: Partial<Record<RailBadgeKey, number>>;
    collapsed: boolean;
    open: boolean;
    compact: boolean;
    username: string;
    roleLabel: string;
    initial: string;
    logoutBusy: boolean;
    homeRouteName?: string;
    navigationLabel?: string;
    brandLabel?: string;
    logoutLabel?: string;
    showSearch?: boolean;
    showReturn?: boolean;
  }>(),
  {
    homeRouteName: "account-home",
    navigationLabel: "后台功能",
    brandLabel: "后台",
    logoutLabel: "退出登录",
    showSearch: true,
    showReturn: true,
  },
);
const emit = defineEmits<{
  "toggle-collapse": [];
  palette: [];
  logout: [];
  navigate: [];
}>();

const root = ref<HTMLElement | null>(null);
const navElement = ref<HTMLElement | null>(null);
const indicator = reactive({ y: 0, h: 0, visible: false, ready: false });
let observer: ResizeObserver | null = null;
let frame = 0;

const modifier =
  typeof navigator !== "undefined" &&
  /mac|iphone|ipad/i.test(navigator.platform || navigator.userAgent)
    ? "⌘"
    : "Ctrl";
const active = computed(() => props.pending || props.current);
const order = computed(
  () =>
    new Map(
      props.sections
        .flatMap((section) => section.items)
        .map((item, index) => [item.name, index]),
    ),
);
const count = (key?: RailBadgeKey): number =>
  key ? (props.badges[key] ?? 0) : 0;
const indicatorStyle = computed(() => ({
  height: `${indicator.h}px`,
  opacity: indicator.visible ? 1 : 0,
  transform: `translate3d(0, ${indicator.y}px, 0)`,
}));

function measure(): void {
  const link = navElement.value?.querySelector<HTMLElement>(
    ".admin-rail__link.is-current",
  );
  if (!link) {
    indicator.visible = false;
    return;
  }
  indicator.y = link.offsetTop;
  indicator.h = link.offsetHeight;
  indicator.visible = true;
}

watch(
  () => [active.value, props.sections, props.collapsed, props.compact],
  async () => {
    await nextTick();
    measure();
  },
  { flush: "post" },
);

onMounted(() => {
  measure();
  const settled =
    typeof document !== "undefined" && document.fonts?.ready
      ? document.fonts.ready
      : Promise.resolve();
  void settled.then(() => {
    measure();
    frame = requestAnimationFrame(() => {
      frame = requestAnimationFrame(() => {
        indicator.ready = true;
      });
    });
  });
  if (typeof ResizeObserver !== "undefined" && navElement.value) {
    observer = new ResizeObserver(() => measure());
    observer.observe(navElement.value);
  }
});
onBeforeUnmount(() => {
  cancelAnimationFrame(frame);
  observer?.disconnect();
});

function onKeydown(event: KeyboardEvent): void {
  const target = event.target as HTMLElement | null;
  if (!target?.classList.contains("admin-rail__link")) return;
  const links = Array.from(
    root.value?.querySelectorAll<HTMLElement>(".admin-rail__link") ?? [],
  );
  const index = links.indexOf(target);
  if (index < 0) return;
  let next = -1;
  if (event.key === "ArrowDown") next = (index + 1) % links.length;
  else if (event.key === "ArrowUp")
    next = (index - 1 + links.length) % links.length;
  else if (event.key === "Home") next = 0;
  else if (event.key === "End") next = links.length - 1;
  if (next < 0) return;
  event.preventDefault();
  links[next]?.focus();
}

defineExpose({
  focusFirst: () =>
    root.value
      ?.querySelector<HTMLElement>(".admin-rail__link, .admin-rail__search")
      ?.focus(),
});
</script>
