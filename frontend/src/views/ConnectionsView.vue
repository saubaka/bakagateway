<template>
  <div v-admin-entrance class="admin-route-panel account-page">
    <section class="managed-page-card">
      <header class="panel-heading">
        <div>
          <h2>应用连接</h2>
          <p>
            管理已同意分享的资料。撤销后应用不能继续取用资料，但它自己的登录状态可能仍需在应用内退出。
          </p>
        </div>
        <button class="button button--soft" :disabled="busy" @click="load">
          刷新连接
        </button>
      </header>
      <AccountFeedback :loading="busy && !loaded" :error="error" />
      <div v-if="loaded && !items.length" class="account-empty">
        <h3>还没有连接的应用</h3>
        <p>从支持baka账号的应用发起登录，同意后会显示在这里。</p>
      </div>
      <ul class="account-device-list">
        <li v-for="item in items" :key="item.id" class="account-device-row">
          <div class="account-device-heading">
            <h3>{{ item.name }}</h3>
            <button
              class="button button--danger"
              :disabled="busy"
              @click="revoke(item)"
            >
              撤销连接
            </button>
          </div>
          <p v-if="!item.active" class="gateway-muted">应用已停用</p>
          <p class="gateway-muted">{{ item.description }}</p>
          <dl class="detail-grid">
            <div>
              <dt>分享内容</dt>
              <dd>
                {{
                  ["openid", "profile", "email", "offline_access"]
                    .filter((s) => item.scopes.includes(s))
                    .map((s) => labels[s])
                    .join("、")
                }}
              </dd>
            </div>
            <div>
              <dt>最近授权</dt>
              <dd>{{ dateLabel(item.lastUsedAt) }}</dd>
            </div>
          </dl>
        </li>
      </ul>
    </section>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from "vue";
import { api } from "../api";
import { useSessionStore } from "../stores/session";
import { useAccountTask, dateLabel } from "../account";
import AccountFeedback from "../components/AccountFeedback.vue";
import { confirmDialog } from "../dialog";
import { notify } from "../notifications";
import { adminEntranceDirective as vAdminEntrance } from "../admin/entrance";
type Connection = {
  id: string;
  name: string;
  description: string;
  scopes: string[];
  lastUsedAt: string;
  active: boolean;
};
const session = useSessionStore(),
  { busy, error, run, isActive } = useAccountTask(),
  loaded = ref(false),
  items = ref<Connection[]>([]);
const labels: Record<string, string> = {
  openid: "基础身份",
  profile: "昵称、账号名与头像",
  email: "邮箱",
  offline_access: "保持连接",
};
async function fetchConnections() {
  const result = await api<{ items: Connection[] }>("/api/account/connections");
  items.value = result.items;
  loaded.value = true;
  return true;
}
async function load() {
  await run(fetchConnections);
}
async function revoke(item: Connection) {
  if (
    busy.value ||
    !(await confirmDialog({
      title: "撤销应用连接？",
      message: `${item.name} 将不能继续取用你的资料。再次使用时需要重新同意。`,
      tone: "danger",
      confirmLabel: "撤销连接",
    }))
  )
    return;
  const done = await run(async () => {
    await session.mutate("/api/account/connections/" + item.id + "/revoke");
    return fetchConnections();
  });
  if (done && isActive()) notify("应用连接已撤销。", "success");
}
onMounted(() => void load());
</script>
