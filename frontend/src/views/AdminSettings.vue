<template>
  <div v-admin-entrance class="admin-route-panel account-page">
    <section class="managed-page-card">
      <header class="panel-heading">
        <div>
          <h2>站点设置</h2>
          <p>公开名称、说明和支持邮箱用于登录页面；注册开关控制自助注册。</p>
        </div>
        <button class="button button--soft" :disabled="busy" @click="load">
          重新读取
        </button>
      </header>
      <AccountFeedback :error="error" />
      <p v-if="busy" role="status">正在处理…</p>
      <form v-if="data" class="form-stack" @submit.prevent="save">
        <fieldset :disabled="busy">
          <label class="field"
            ><span>站点名称</span
            ><input v-model="data.siteName" required maxlength="60" /></label
          ><label class="field"
            ><span>站点说明</span
            ><textarea
              v-model="data.description"
              maxlength="200"
              rows="3"
            /></label
          ><label class="field"
            ><span>支持邮箱（可选）</span
            ><input
              v-model="data.supportEmail"
              type="email"
              maxlength="254" /></label
          ><label class="admin-check"
            ><input
              v-model="data.registrationOpen"
              type="checkbox"
            />开放自助注册</label
          >
          <p class="gateway-muted">
            开启前需配置邮件服务。关闭后，已有账号仍可登录。
          </p>
        </fieldset>
        <button class="button button--primary" :disabled="busy">
          保存设置
        </button>
      </form>
    </section>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from "vue";
import { api } from "../api";
import { adminWrite } from "../admin";
import { useAccountTask } from "../account";
import { refreshSite } from "../siteInfo";
import { notify } from "../notifications";
import AccountFeedback from "../components/AccountFeedback.vue";
import { adminEntranceDirective as vAdminEntrance } from "../admin/entrance";
type Settings = {
  siteName: string;
  description: string;
  supportEmail: string;
  registrationOpen: boolean;
  version: number;
};
const data = ref<Settings>();
const { busy, error, run, isActive } = useAccountTask();
async function load() {
  await run(async () => {
    const v = await api<Settings>("/api/admin/settings");
    if (isActive()) data.value = v;
  });
}
async function save() {
  await run(async () => {
    if (!data.value) return;
    const { version, ...body } = data.value;
    const v = await adminWrite<Settings>(
      "/api/admin/settings",
      { ...body, expectedVersion: version },
      "保存站点资料与注册开关。",
    );
    if (v && isActive()) {
      data.value = v;
      await refreshSite();
      notify("站点设置已保存。");
    }
  });
}
onMounted(load);
</script>
