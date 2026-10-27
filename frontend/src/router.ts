import { createRouter, createWebHistory } from "vue-router";
import { siteInfo } from "./siteInfo";
import { useSessionStore } from "./stores/session";
export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/account" },
    ...Object.entries({
      "/login": ["登录", "login"],
      "/register": ["注册", "register"],
      "/forgot-password": ["找回密码", "forgot"],
      "/verify-email": ["验证邮箱", "verify"],
      "/reset-password": ["设置新密码", "reset"],
    }).map(([path, [title, authMode]]) => ({
      path,
      component: () => import("./views/AuthView.vue"),
      meta: { title, authMode },
    })),
    {
      path: "/account",
      component: () => import("./views/AccountLayout.vue"),
      meta: { requiresAuth: true },
      children: [
        {
          path: "",
          name: "account-home",
          component: () => import("./views/AccountHome.vue"),
          meta: { title: "我的主页" },
        },
        {
          path: "profile",
          name: "account-profile",
          component: () => import("./views/AccountProfile.vue"),
          meta: { title: "个人资料" },
        },
        {
          path: "security",
          name: "account-security",
          component: () => import("./views/AccountSecurity.vue"),
          meta: { title: "账号安全" },
        },
        {
          path: "devices",
          name: "account-devices",
          component: () => import("./views/AccountDevices.vue"),
          meta: { title: "登录设备" },
        },
        {
          path: "connections",
          name: "account-connections",
          component: () => import("./views/ConnectionsView.vue"),
          meta: { title: "已连接应用" },
        },
      ],
    },
    {
      path: "/admin",
      component: () => import("./views/AdminLayout.vue"),
      meta: { requiresAuth: true, requiresAdmin: true },
      children: [
        {
          path: "",
          name: "admin-home",
          component: () => import("./views/AdminOverview.vue"),
          meta: { title: "平台概览" },
        },
        {
          path: "users",
          name: "admin-users",
          component: () => import("./views/AdminUsers.vue"),
          meta: { title: "用户管理" },
        },
        {
          path: "clients",
          name: "admin-clients",
          component: () => import("./views/AdminClients.vue"),
          meta: { title: "接入应用" },
        },
        {
          path: "mail",
          name: "admin-mail",
          component: () => import("./views/AdminMail.vue"),
          meta: { title: "邮件设置" },
        },
        {
          path: "settings",
          name: "admin-settings",
          component: () => import("./views/AdminSettings.vue"),
          meta: { title: "站点设置" },
        },
        {
          path: "audit",
          name: "admin-audit",
          component: () => import("./views/AdminAudit.vue"),
          meta: { title: "操作记录" },
        },
      ],
    },
    {
      path: "/unavailable",
      component: () => import("./views/UnavailableView.vue"),
      meta: { title: "服务暂时不可用" },
    },
    {
      path: "/forbidden",
      component: () => import("./views/ForbiddenView.vue"),
      meta: { title: "无权访问" },
    },
    {
      path: "/authorize",
      component: () => import("./views/AuthorizeView.vue"),
      meta: { title: "登录应用", requiresAuth: true },
    },
    {
      path: "/:pathMatch(.*)*",
      component: () => import("./views/NotFound.vue"),
      meta: { title: "页面不存在" },
    },
  ],
  scrollBehavior: () => ({ top: 0 }),
});
router.beforeEach(async (to) => {
  if (to.meta.requiresAuth) {
    const session = useSessionStore();
    try {
      await session.refresh();
    } catch {
      return { path: "/unavailable", query: { next: to.fullPath } };
    }
    if (!session.user) return { path: "/login", query: { next: to.fullPath } };
    if (to.meta.requiresAdmin && session.user.role !== "admin")
      return "/forbidden";
  }
});
router.afterEach((route) => {
  document.title = `${route.meta.title ?? "baka"} · ${siteInfo.siteName}`;
});
