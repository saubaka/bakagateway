<template>
  <div v-admin-entrance class="admin-route-panel account-page">
    <section class="managed-page-card">
      <header class="panel-heading">
        <div>
          <h2>平台概览</h2>
          <p>查看账号、接入应用与最近的管理操作。</p>
        </div>
        <button class="button button--soft" :disabled="busy" @click="load">
          刷新
        </button>
      </header>
      <AccountFeedback :error="error" />
      <p v-if="busy" role="status">正在读取…</p>
      <dl v-if="data" class="detail-grid">
        <div v-for="(label, key) in labels" :key="key">
          <dt>{{ label }}</dt>
          <dd>{{ data.counts[key] }}</dd>
        </div>
      </dl>
    </section>
    <section v-if="data" class="managed-page-card">
      <header class="panel-heading">
        <h2>最近操作</h2>
        <router-link class="button button--soft" to="/admin/audit"
          >全部记录</router-link
        >
      </header>
      <p v-if="!data.recent.length" class="gateway-muted">
        还没有管理操作记录。
      </p>
      <ul class="admin-records">
        <li v-for="row in data.recent" :key="row.id">
          <strong>{{ actionLabels[row.action] ?? row.action }}</strong
          ><span>{{ row.actorName }} · {{ dateLabel(row.createdAt) }}</span>
          <p>{{ row.summary }}</p>
        </li>
      </ul>
    </section>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from "vue";
import { api } from "../api";
import { useAccountTask, dateLabel } from "../account";
import { actionLabels, type Audit } from "../admin";
import AccountFeedback from "../components/AccountFeedback.vue";
import { adminEntranceDirective as vAdminEntrance } from "../admin/entrance";
const { busy, error, run, isActive } = useAccountTask();
const labels = {
  users: "全部用户",
  activeUsers: "启用用户",
  admins: "启用管理员",
  clients: "接入应用",
  activeClients: "启用应用",
  connections: "未撤销连接",
};
const data = ref<{ counts: Record<string, number>; recent: Audit[] }>();
async function load() {
  await run(async () => {
    const v = await api<typeof data.value>("/api/admin/overview");
    if (isActive()) data.value = v;
  });
}
onMounted(load);
</script>
