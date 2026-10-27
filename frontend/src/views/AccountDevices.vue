<template>
  <div v-admin-entrance class="admin-route-panel account-page">
    <section class="managed-page-card">
      <header class="panel-heading">
        <div>
          <h2>已登录的设备</h2>
          <p>只显示仍然有效的登录，退出后该设备需要重新验证身份。</p>
        </div>
        <div class="button-row">
          <button class="button button--soft" :disabled="busy" @click="load">
            刷新列表</button
          ><button
            class="button button--danger"
            :disabled="busy || total <= 1"
            @click="revokeOthers"
          >
            退出其他设备
          </button>
        </div>
      </header>
      <AccountFeedback :loading="busy && !loaded" :error="error" />
      <p v-if="loaded" class="gateway-muted">
        共{{ total }}个有效登录{{
          total > items.length ? "，显示最近100个" : ""
        }}。
      </p>
      <ul class="account-device-list">
        <li
          v-for="item in items"
          :key="item.id"
          class="account-device-row"
          :data-device-id="item.id"
        >
          <div class="account-device-heading">
            <h3>{{ item.label }}</h3>
            <span v-if="item.current" class="badge badge--blue">当前设备</span
            ><button
              v-else
              class="button button--soft"
              :disabled="busy"
              @click="revoke(item)"
            >
              退出此设备
            </button>
          </div>
          <dl class="detail-grid">
            <div>
              <dt>来源地址</dt>
              <dd>{{ item.ipAddress || "未知来源" }}</dd>
            </div>
            <div>
              <dt>登录时间</dt>
              <dd>{{ dateLabel(item.createdAt) }}</dd>
            </div>
            <div>
              <dt>最近活动</dt>
              <dd>{{ dateLabel(item.lastSeenAt) }}</dd>
            </div>
            <div>
              <dt>到期时间</dt>
              <dd>{{ dateLabel(item.expiresAt) }}</dd>
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
import { useAccountTask, dateLabel, type Device } from "../account";
import AccountFeedback from "../components/AccountFeedback.vue";
import { confirmDialog } from "../dialog";
import { notify } from "../notifications";
import { adminEntranceDirective as vAdminEntrance } from "../admin/entrance";
const session = useSessionStore(),
  { busy, error, run, isActive } = useAccountTask(),
  items = ref<Device[]>([]),
  total = ref(0),
  loaded = ref(false);
async function fetchDevices() {
  const result = await api<{ items: Device[]; total: number }>(
    "/api/account/sessions",
  );
  items.value = result.items;
  total.value = result.total;
  loaded.value = true;
  return true;
}
async function load() {
  await run(fetchDevices);
}
async function revoke(item: Device) {
  if (
    busy.value ||
    !(await confirmDialog({
      title: "退出这个设备？",
      message: `${item.label} 将需要重新登录，当前设备继续使用。`,
      confirmLabel: "退出设备",
      tone: "danger",
    }))
  )
    return;
  const done = await run(async () => {
    await session.mutate(`/api/account/sessions/${item.id}/revoke`);
    return fetchDevices();
  });
  if (done && isActive()) notify("该设备已退出。", "success");
}
async function revokeOthers() {
  if (
    busy.value ||
    !(await confirmDialog({
      title: "退出其他设备？",
      message: "其他设备上的登录将失效，当前设备继续使用。",
      confirmLabel: "退出其他设备",
      tone: "danger",
    }))
  )
    return;
  const done = await run(async () => {
    await session.mutate("/api/account/sessions/revoke-others");
    return fetchDevices();
  });
  if (done && isActive()) notify("其他设备已退出。", "success");
}
onMounted(() => void load());
</script>
