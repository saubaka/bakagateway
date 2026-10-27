<template>
  <div v-admin-entrance class="admin-route-panel account-page">
    <AccountFeedback :loading="busy && !loaded" :error="error" />
    <button v-if="!loaded && error" class="button button--soft" @click="load">
      重试读取
    </button>
    <template v-if="loaded">
      <section class="managed-page-card">
        <header class="panel-heading">
          <div>
            <h2>修改密码</h2>
            <p>修改后所有设备都需要重新登录，包含当前设备。</p>
          </div>
        </header>
        <form
          class="form-stack account-form"
          :aria-busy="busy"
          @submit.prevent="changePassword"
        >
          <PasswordField
            v-model="oldPassword"
            label="当前密码"
            :required="true"
            :disabled="busy"
          />
          <PasswordField
            v-model="newPassword"
            label="新密码"
            autocomplete="new-password"
            :required="true"
            :disabled="busy"
          />
          <PasswordField
            v-model="confirmation"
            label="确认新密码"
            autocomplete="new-password"
            :required="true"
            :disabled="busy"
          />
          <p class="gateway-muted">新密码使用12–128个字符。</p>
          <div class="button-row">
            <button
              class="button button--primary"
              type="submit"
              :disabled="busy"
            >
              {{ busy ? "正在处理…" : "更新密码" }}
            </button>
          </div>
        </form>
      </section>
      <section class="managed-page-card">
        <header class="panel-heading">
          <div>
            <h2>更换邮箱</h2>
            <p>
              当前邮箱：<span class="account-wrap">{{
                session.user?.email
              }}</span>
            </p>
          </div>
        </header>
        <p class="gateway-muted">
          验证新邮箱后才会更换，旧邮箱会收到提醒；完成后请重新登录。
        </p>
        <form
          v-if="!flow"
          class="form-stack account-form"
          :aria-busy="busy"
          @submit.prevent="startEmail"
        >
          <label class="field"
            ><span class="field__label">新邮箱</span
            ><input
              v-model="newEmail"
              type="email"
              autocomplete="email"
              maxlength="254"
              required
              :disabled="busy"
          /></label>
          <PasswordField
            v-model="emailPassword"
            label="验证当前密码"
            :required="true"
            :disabled="busy"
          />
          <div class="button-row">
            <button
              class="button button--primary"
              type="submit"
              :disabled="busy"
            >
              发送邮箱验证码
            </button>
          </div>
        </form>
        <div v-else class="account-form">
          <p role="status">验证码已发送至 {{ flow.emailHint }}。</p>
          <p v-if="expired" class="gateway-problem">验证已过期，请重新开始。</p>
          <form
            v-else
            class="form-stack"
            :aria-busy="busy"
            @submit.prevent="verifyEmail"
          >
            <label class="field"
              ><span class="field__label">邮箱验证码</span
              ><input
                v-model="code"
                inputmode="numeric"
                autocomplete="one-time-code"
                pattern="[0-9]{6}"
                minlength="6"
                maxlength="6"
                required
                :disabled="busy"
            /></label>
            <div class="button-row">
              <button
                class="button button--primary"
                type="submit"
                :disabled="busy"
              >
                确认更换邮箱</button
              ><button
                class="button button--soft"
                type="button"
                :disabled="busy || countdown > 0"
                @click="resend"
              >
                {{ countdown > 0 ? `${countdown}秒后可重发` : "重发验证码" }}
              </button>
            </div>
          </form>
          <button
            class="gateway-text-button account-restart"
            type="button"
            :disabled="busy"
            @click="
              flow = null;
              code = '';
            "
          >
            重新开始邮箱更换
          </button>
        </div>
      </section>
    </template>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api";
import { useSessionStore, type Session, type User } from "../stores/session";
import { useAccountTask, type EmailFlow } from "../account";
import { notify } from "../notifications";
import PasswordField from "../components/PasswordField.vue";
import AccountFeedback from "../components/AccountFeedback.vue";
import { adminEntranceDirective as vAdminEntrance } from "../admin/entrance";
const session = useSessionStore(),
  router = useRouter(),
  { busy, error, run, isActive } = useAccountTask();
const loaded = ref(false),
  oldPassword = ref(""),
  newPassword = ref(""),
  confirmation = ref(""),
  newEmail = ref(""),
  emailPassword = ref(""),
  code = ref(""),
  flow = ref<EmailFlow | null>(null),
  clock = ref(Date.now());
const countdown = computed(() =>
  flow.value
    ? Math.max(
        0,
        Math.ceil((Date.parse(flow.value.resendAt) - clock.value) / 1000),
      )
    : 0,
);
const expired = computed(
  () => !!flow.value && Date.parse(flow.value.expiresAt) <= clock.value,
);
async function load() {
  await run(async () => {
    const [profile, result] = await Promise.all([
      api<{ user: User }>("/api/account/profile"),
      api<{ flow: EmailFlow | null }>("/api/account/email/flow"),
    ]);
    session.updateUser(profile.user);
    flow.value = result.flow;
    loaded.value = true;
    return true;
  });
}
async function finish(result: { session: Session }, message: string) {
  session.accept(result.session);
  if (isActive()) {
    notify(message, "success");
    await router.replace({
      path: "/login",
      query: { next: "/account/security" },
    });
  }
}
async function changePassword() {
  if (
    newPassword.value.length < 12 ||
    newPassword.value.length > 128 ||
    newPassword.value !== confirmation.value
  ) {
    error.value = "新密码须为12–128个字符，且两次输入一致。";
    return;
  }
  const result = await run(() =>
    session.mutate<{ session: Session }>("/api/account/password", {
      currentPassword: oldPassword.value,
      password: newPassword.value,
      confirmPassword: confirmation.value,
    }),
  );
  oldPassword.value = "";
  newPassword.value = "";
  confirmation.value = "";
  if (result) await finish(result, "密码已更新，请重新登录。");
}
async function startEmail() {
  const result = await run(() =>
    session.mutate<{ flow: EmailFlow }>("/api/account/email/start", {
      email: newEmail.value,
      currentPassword: emailPassword.value,
    }),
  );
  emailPassword.value = "";
  if (result) {
    flow.value = result.flow;
    code.value = "";
    if (isActive()) notify("验证邮件已发送。", "success");
  }
}
async function resend() {
  const result = await run(() =>
    session.mutate<{ flow: EmailFlow }>("/api/account/email/resend"),
  );
  if (result) {
    flow.value = result.flow;
    code.value = "";
    if (isActive()) notify("验证码已重新发送。", "success");
  }
}
async function verifyEmail() {
  const result = await run(() =>
    session.mutate<{ session: Session }>("/api/account/email/verify", {
      code: code.value,
    }),
  );
  code.value = "";
  if (result) await finish(result, "邮箱已更新，请重新登录。");
}
let timer: ReturnType<typeof setInterval>;
onMounted(() => {
  void load();
  timer = setInterval(() => (clock.value = Date.now()), 1000);
});
onBeforeUnmount(() => {
  clearInterval(timer);
  oldPassword.value = "";
  newPassword.value = "";
  confirmation.value = "";
  emailPassword.value = "";
  code.value = "";
});
</script>
