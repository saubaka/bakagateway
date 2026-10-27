<template>
  <div v-admin-entrance class="admin-route-panel account-page">
    <section class="managed-page-card">
      <header class="panel-heading">
        <div>
          <h2>操作记录</h2>
          <p>记录成功的关键管理操作，不包含密码、接入密钥或登录凭据。</p>
        </div>
        <button class="button button--soft" :disabled="busy" @click="load">
          刷新
        </button>
      </header>
      <form class="admin-search" @submit.prevent="search">
        <label class="field"
          ><span>操作类型</span
          ><select v-model="action" :disabled="busy">
            <option value="">全部操作</option>
            <option
              v-for="(label, key) in actionLabels"
              :key="key"
              :value="key"
            >
              {{ label }}
            </option>
          </select></label
        ><button class="button button--soft" :disabled="busy">筛选</button>
      </form>
      <AccountFeedback :error="error" />
      <p v-if="busy" role="status">正在读取…</p>
      <template v-if="data"
        ><ul class="admin-records">
          <li v-for="row in data.items" :key="row.id">
            <strong>{{ actionLabels[row.action] ?? row.action }}</strong
            ><span>{{ row.actorName }} · {{ dateLabel(row.createdAt) }}</span>
            <p>{{ row.summary }}</p>
            <p v-if="row.targetId" class="gateway-muted">
              目标：{{ row.targetId }}
            </p>
          </li>
        </ul>
        <p v-if="!data.items.length" class="gateway-muted">
          没有符合条件的操作记录。
        </p>
        <AdminPager v-bind="data" :busy="busy" @change="go"
      /></template>
    </section>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from "vue";
import { api } from "../api";
import { useAccountTask, dateLabel } from "../account";
import { actionLabels, type Page, type Audit } from "../admin";
import AccountFeedback from "../components/AccountFeedback.vue";
import AdminPager from "../components/AdminPager.vue";
import { adminEntranceDirective as vAdminEntrance } from "../admin/entrance";
const { busy, error, run, isActive } = useAccountTask();
const data = ref<Page<Audit>>(),
  action = ref(""),
  page = ref(1);
let applied = "";
async function load() {
  await run(async () => {
    const value = await api<Page<Audit>>(
      "/api/admin/audit?" +
        new URLSearchParams({ action: applied, page: String(page.value) }),
    );
    if (isActive()) data.value = value;
  });
}
function search() {
  applied = action.value;
  page.value = 1;
  void load();
}
function go(n: number) {
  page.value = n;
  void load();
}
onMounted(load);
</script>
