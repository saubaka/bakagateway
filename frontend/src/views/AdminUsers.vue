<template>
  <div v-admin-entrance class="admin-route-panel account-page">
    <section class="managed-page-card">
      <header class="panel-heading">
        <div>
          <h2>用户管理</h2>
          <p>调整账号状态与角色；变更后会撤销该账号的旧登录和应用凭据。</p>
        </div>
        <button class="button button--soft" :disabled="busy" @click="load">
          刷新
        </button>
      </header>
      <form class="admin-search" @submit.prevent="search">
        <label class="field"
          ><span>搜索用户</span
          ><input
            v-model="query"
            maxlength="80"
            placeholder="账号名、昵称或邮箱"
            :disabled="busy" /></label
        ><label class="field"
          ><span>账号状态</span
          ><select v-model="status" :disabled="busy">
            <option value="all">全部状态</option>
            <option value="active">启用</option>
            <option value="inactive">停用</option>
          </select></label
        ><label class="field"
          ><span>角色</span
          ><select v-model="role" :disabled="busy">
            <option value="all">全部角色</option>
            <option value="user">普通用户</option>
            <option value="admin">管理员</option>
          </select></label
        ><button class="button button--soft" :disabled="busy">筛选</button>
      </form>
      <AccountFeedback :error="error" />
      <p v-if="busy" role="status">正在处理…</p>
      <div v-if="data" class="admin-list">
        <article v-for="row in data.items" :key="row.id" class="admin-list-row">
          <div>
            <h3>
              {{ row.nickname }} <small>{{ row.username }}</small>
            </h3>
            <p>{{ row.email }}</p>
            <p class="gateway-muted">
              {{ row.role === "admin" ? "管理员" : "普通用户" }} ·
              {{ row.active ? "启用" : "停用" }} ·
              {{ dateLabel(row.createdAt) }}
            </p>
          </div>
          <div class="button-row">
            <button
              class="button button--soft"
              :disabled="busy"
              :aria-label="`${row.active ? '停用' : '启用'} ${row.username}`"
              @click="change(row, !row.active, row.role)"
            >
              {{ row.active ? "停用" : "启用" }}</button
            ><button
              class="button button--soft"
              :disabled="busy"
              :aria-label="`${row.role === 'admin' ? '设为普通用户' : '设为管理员'}，更改 ${row.username} 的角色`"
              @click="
                change(row, row.active, row.role === 'admin' ? 'user' : 'admin')
              "
            >
              {{ row.role === "admin" ? "设为普通用户" : "设为管理员" }}
            </button>
          </div>
        </article>
        <p v-if="!data.items.length" class="gateway-muted">
          没有符合条件的用户。
        </p>
        <AdminPager v-bind="data" :busy="busy" @change="go" />
      </div>
    </section>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api";
import { useAccountTask, dateLabel } from "../account";
import { adminWrite, type Page, type AdminUser } from "../admin";
import { useSessionStore } from "../stores/session";
import AccountFeedback from "../components/AccountFeedback.vue";
import AdminPager from "../components/AdminPager.vue";
import { notify } from "../notifications";
import { adminEntranceDirective as vAdminEntrance } from "../admin/entrance";
const { busy, error, run, isActive } = useAccountTask();
const router = useRouter(),
  session = useSessionStore();
const data = ref<Page<AdminUser>>(),
  query = ref(""),
  status = ref("all"),
  role = ref("all"),
  page = ref(1);
let applied = { q: "", status: "all", role: "all" };
async function fetchRows() {
  const value = await api<Page<AdminUser>>(
    "/api/admin/users?" +
      new URLSearchParams({ ...applied, page: String(page.value) }),
  );
  if (isActive()) data.value = value;
}
async function load() {
  await run(fetchRows);
}
function search() {
  applied = { q: query.value, status: status.value, role: role.value };
  page.value = 1;
  void load();
}
function go(n: number) {
  page.value = n;
  void load();
}
async function change(
  row: AdminUser,
  active: boolean,
  role: AdminUser["role"],
) {
  await run(async () => {
    const v = await adminWrite<{ sessionInvalidated: boolean }>(
      `/api/admin/users/${row.id}`,
      { active, role, expectedVersion: row.version },
      `将 ${row.username} 设为${active ? "启用" : "停用"}的${role === "admin" ? "管理员" : "普通用户"}。旧登录与应用凭据会失效，至少需保留一位启用管理员。`,
    );
    if (!v) return;
    notify("账号已更新。");
    if (v.sessionInvalidated) {
      session.invalidate();
      await router.replace("/login");
      return;
    }
    await fetchRows();
  });
}
onMounted(load);
</script>
