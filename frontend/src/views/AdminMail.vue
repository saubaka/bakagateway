<template>
  <div v-admin-entrance class="admin-route-panel account-page">
    <section class="managed-page-card">
      <header class="panel-heading">
        <div>
          <h2>邮件设置</h2>
          <p>
            用于注册、找回密码和账号提醒。保存前会验证连接，密码加密保存且不回传。
          </p>
        </div>
        <button class="button button--soft" :disabled="busy" @click="load">
          重新读取
        </button>
      </header>
      <AccountFeedback :error="error" />
      <p v-if="busy" role="status">正在处理…</p>
      <form v-if="data" class="form-stack" @submit.prevent="save">
        <p class="gateway-muted">
          {{
            data.configured
              ? "已保存配置；可发送测试邮件确认投递。"
              : "尚未配置。"
          }}
          {{ data.passwordConfigured ? "已有保存的SMTP密码。" : "" }}
        </p>
        <fieldset :disabled="busy">
          <div class="admin-edit-grid">
            <label class="field"
              ><span>SMTP主机</span
              ><input v-model="data.host" required maxlength="253" /></label
            ><label class="field"
              ><span>端口</span
              ><input
                v-model.number="data.port"
                type="number"
                min="1"
                max="65535"
                required /></label
            ><label class="field"
              ><span>连接安全</span
              ><select v-model="data.security">
                <option value="starttls">STARTTLS</option>
                <option value="tls">TLS</option>
                <option value="plain">本地测试明文（生产禁用）</option>
              </select></label
            ><label class="field"
              ><span>发件地址</span
              ><input
                v-model="data.sender"
                type="email"
                maxlength="254"
                required /></label
            ><label class="field"
              ><span>SMTP用户名（可选）</span
              ><input
                v-model="data.username"
                maxlength="254"
                autocomplete="off" /></label
            ><PasswordField
              v-model="password"
              label="SMTP密码（留空保留已有值）"
              autocomplete="new-password"
            />
          </div>
          <p class="gateway-muted">
            更换主机或用户名时需重新输入密码；用户名留空表示不使用SMTP认证。
          </p>
        </fieldset>
        <button class="button button--primary" :disabled="busy">
          验证连接并保存
        </button>
      </form>
    </section>
    <section v-if="data?.configured" class="managed-page-card">
      <header class="panel-heading">
        <div>
          <h2>测试发信</h2>
          <p>使用已保存配置发送一封测试邮件，失败会给出提示。</p>
        </div>
      </header>
      <form class="form-stack" @submit.prevent="test">
        <label class="field"
          ><span>测试收件邮箱</span
          ><input
            v-model="recipient"
            required
            type="email"
            maxlength="254"
            :disabled="busy" /></label
        ><button class="button button--soft" :disabled="busy">
          发送测试邮件
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
import { useSessionStore } from "../stores/session";
import { notify } from "../notifications";
import AccountFeedback from "../components/AccountFeedback.vue";
import PasswordField from "../components/PasswordField.vue";
import { adminEntranceDirective as vAdminEntrance } from "../admin/entrance";
type Mail = {
  configured: boolean;
  version: number;
  host: string;
  port: number;
  sender: string;
  security: string;
  username: string;
  passwordConfigured: boolean;
};
const data = ref<Mail>(),
  password = ref(""),
  recipient = ref(useSessionStore().user?.email ?? "");
const { busy, error, run, isActive } = useAccountTask();
async function load() {
  await run(async () => {
    const v = await api<Mail>("/api/admin/mail");
    if (isActive()) {
      data.value = v;
      password.value = "";
    }
  });
}
async function save() {
  await run(async () => {
    if (!data.value) return;
    const { configured, passwordConfigured, version, ...body } = data.value;
    try {
      const v = await adminWrite<Mail>(
        "/api/admin/mail",
        { ...body, password: password.value, expectedVersion: version },
        "验证邮件服务器连接与认证，成功后保存新配置。",
      );
      if (v && isActive()) {
        data.value = v;
        notify("邮件连接已验证，配置已保存。");
      }
    } finally {
      password.value = "";
    }
  });
}
async function test() {
  await run(async () => {
    const v = await adminWrite(
      "/api/admin/mail/test",
      { recipient: recipient.value },
      `向 ${recipient.value} 发送一封测试邮件。`,
    );
    if (v) notify("测试邮件已提交，请检查收件箱。");
  });
}
onMounted(load);
</script>
