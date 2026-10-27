<template>
  <div class="admin-shell has-rail" :class="{ 'is-collapsed': collapsed }">
    <button
      class="admin-drawer-backdrop"
      :class="{ 'is-open': menuOpen }"
      type="button"
      tabindex="-1"
      aria-label="关闭管理后台导航"
      @click="closeMenu"
    />
    <AdminRail
      ref="rail"
      :sections="sections"
      :current="String(route.name ?? '')"
      :badges="{}"
      :collapsed="collapsed"
      :open="menuOpen"
      :compact="compact"
      :username="session.user?.nickname ?? ''"
      role-label="管理后台"
      :initial="session.user?.nickname.slice(0, 1) ?? 'B'"
      :logout-busy="busy"
      home-route-name="admin-home"
      navigation-label="管理后台"
      brand-label="管理后台"
      logout-label="退出登录"
      :show-search="false"
      :show-return="false"
      @toggle-collapse="collapsed = !collapsed"
      @navigate="closeMenu"
      @logout="logout"
    />
    <div class="admin-workspace" :inert="compact && menuOpen">
      <header class="admin-topbar">
        <button
          ref="menuButton"
          class="icon-button admin-menu-button"
          type="button"
          aria-controls="admin-sidebar"
          :aria-expanded="menuOpen"
          aria-label="打开管理后台导航"
          @click="openMenu"
        >
          <AdminIcon name="panel" :size="20" />
        </button>
        <div class="admin-topbar__title">
          <span class="eyebrow">BAKA IDENTITY</span>
          <h1>{{ route.meta.title }}</h1>
        </div>
        <div class="admin-topbar__actions">
          <router-link class="button button--soft" to="/account"
            >个人中心</router-link
          >
          <button class="button button--soft" :disabled="busy" @click="logout">
            {{ busy ? "正在退出…" : "退出登录" }}
          </button>
        </div>
      </header>
      <main id="main-content" class="admin-main account-main" tabindex="-1">
        <AccountFeedback :error="error" />
        <router-view v-slot="{ Component, route: child }"
          ><component :is="Component" :key="child.path"
        /></router-view>
      </main>
    </div>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import AdminRail from "../components/admin/AdminRail.vue";
import AdminIcon from "../components/admin/AdminIcon.vue";
import AccountFeedback from "../components/AccountFeedback.vue";
import type { RailSection } from "../admin/navModel";
import { useSessionStore, type Session } from "../stores/session";
import { useAccountTask } from "../account";
const route = useRoute(),
  router = useRouter(),
  session = useSessionStore();
const { busy, error, run } = useAccountTask();
const menuOpen = ref(false),
  collapsed = ref(false),
  compact = ref(false),
  rail = ref<InstanceType<typeof AdminRail> | null>(null),
  menuButton = ref<HTMLElement | null>(null);
const sections: RailSection[] = [
  {
    key: "main",
    label: "平台管理",
    items: [
      {
        name: "admin-home",
        label: "平台概览",
        icon: "overview",
        permission: "",
        section: "main",
        keywords: "",
        shortcut: "h",
      },
      {
        name: "admin-users",
        label: "用户管理",
        icon: "accounts",
        permission: "",
        section: "main",
        keywords: "",
        shortcut: "u",
      },
      {
        name: "admin-clients",
        label: "接入应用",
        icon: "panel",
        permission: "",
        section: "main",
        keywords: "",
        shortcut: "a",
      },
      {
        name: "admin-mail",
        label: "邮件设置",
        icon: "mail",
        permission: "",
        section: "main",
        keywords: "",
        shortcut: "m",
      },
      {
        name: "admin-settings",
        label: "站点设置",
        icon: "system",
        permission: "",
        section: "main",
        keywords: "",
        shortcut: "s",
      },
      {
        name: "admin-audit",
        label: "操作记录",
        icon: "clock",
        permission: "",
        section: "main",
        keywords: "",
        shortcut: "l",
      },
    ],
  },
];
let query: MediaQueryList;
let goPending = false;
let goTimer: ReturnType<typeof setTimeout>;
watch(
  () => route.path,
  async () => {
    closeMenu();
    await nextTick();
    document.getElementById("main-content")?.focus({ preventScroll: true });
  },
);
function updateCompact() {
  compact.value = query.matches;
  if (!compact.value) closeMenu();
}
async function openMenu() {
  menuOpen.value = true;
  document.body.style.overflow = "hidden";
  await nextTick();
  // Wait for the drawer visibility transition to apply before moving focus.
  await new Promise<void>((resolve) =>
    requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
  );
  if (menuOpen.value) rail.value?.focusFirst();
}
function closeMenu() {
  const was = menuOpen.value;
  menuOpen.value = false;
  document.body.style.overflow = "";
  if (was) menuButton.value?.focus();
}
function keydown(event: KeyboardEvent) {
  const target = event.target as HTMLElement | null;
  if (
    !document.querySelector("dialog[open]") &&
    !event.ctrlKey &&
    !event.metaKey &&
    !event.altKey &&
    !target?.closest("input,textarea,select,[contenteditable=true]")
  ) {
    if (goPending) {
      goPending = false;
      clearTimeout(goTimer);
      const item = sections
        .flatMap((section) => section.items)
        .find((item) => item.shortcut === event.key.toLowerCase());
      if (item) {
        event.preventDefault();
        void router.push({ name: item.name });
      }
    } else if (event.key.toLowerCase() === "g") {
      goPending = true;
      goTimer = setTimeout(() => (goPending = false), 1000);
    }
  }
  if (!compact.value || !menuOpen.value) return;
  if (event.key === "Escape") {
    event.preventDefault();
    closeMenu();
  }
  if (event.key === "Tab") {
    const items = Array.from(
      document.querySelectorAll<HTMLElement>(
        "#admin-sidebar a,#admin-sidebar button:not([disabled])",
      ),
    );
    const first = items[0],
      last = items.at(-1);
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last?.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first?.focus();
    }
  }
}
async function logout() {
  await run(async () => {
    const result = await session.mutate<{ session: Session }>(
      "/api/auth/logout",
    );
    session.accept(result.session);
    await router.replace("/login");
    return true;
  });
}
onMounted(() => {
  query = matchMedia("(max-width:900px)");
  updateCompact();
  query.addEventListener("change", updateCompact);
  document.addEventListener("keydown", keydown);
});
onBeforeUnmount(() => {
  clearTimeout(goTimer);
  query?.removeEventListener("change", updateCompact);
  document.removeEventListener("keydown", keydown);
  document.body.style.overflow = "";
});
</script>
