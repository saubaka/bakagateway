<template>
  <div v-admin-entrance class="admin-route-panel account-page">
    <section class="managed-page-card account-welcome">
      <span class="avatar account-avatar" aria-hidden="true"
        ><img
          v-if="session.user?.avatarUrl"
          :src="session.user.avatarUrl"
          alt=""
        /><template v-else>{{
          session.user?.nickname.slice(0, 1)
        }}</template></span
      >
      <div>
        <span class="eyebrow">我的账号</span>
        <h2>你好，{{ session.user?.nickname }}。</h2>
        <p class="gateway-muted">在这里管理你的资料与账号安全。</p>
      </div>
    </section>
    <section class="managed-page-card">
      <header class="panel-heading"><h2>账号信息</h2></header>
      <dl class="detail-grid">
        <div>
          <dt>账号名</dt>
          <dd>{{ session.user?.username }}</dd>
        </div>
        <div>
          <dt>邮箱</dt>
          <dd>{{ session.user?.email }}</dd>
        </div>
        <div>
          <dt>邮箱状态</dt>
          <dd>{{ session.user?.emailVerified ? "已验证" : "待验证" }}</dd>
        </div>
      </dl>
    </section>
    <router-link
      v-if="session.user?.role === 'admin'"
      class="button button--soft"
      to="/admin"
      >管理后台</router-link
    >
    <div class="account-shortcuts">
      <router-link
        v-for="item in links"
        :key="item.to"
        class="managed-page-card account-shortcut"
        :to="item.to"
        ><h2>{{ item.title }} <span aria-hidden="true">↗</span></h2>
        <p>{{ item.description }}</p></router-link
      >
    </div>
  </div>
</template>
<script setup lang="ts">
import { useSessionStore } from "../stores/session";
import { adminEntranceDirective as vAdminEntrance } from "../admin/entrance";
const session = useSessionStore();
const links = [
  {
    to: "/account/profile",
    title: "个人资料",
    description: "更新昵称与头像。",
  },
  {
    to: "/account/security",
    title: "账号安全",
    description: "更换邮箱、修改密码。",
  },
  {
    to: "/account/devices",
    title: "登录设备",
    description: "查看设备，退出不再使用的登录。",
  },
  {
    to: "/account/connections",
    title: "已连接应用",
    description: "查看和撤销已同意的应用连接。",
  },
];
</script>
