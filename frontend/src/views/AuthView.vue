<template>
  <AuthFrame :title="title" :description="description">
    <p
      v-if="loading"
      class="gateway-muted"
      :class="{ 'visually-hidden': mode === 'login' }"
      role="status"
    >
      正在加载…
    </p>
    <p v-if="error" class="gateway-problem" role="alert">{{ error }}</p>
    <button
      v-if="bootFailed"
      class="button button--soft"
      :disabled="loading"
      type="button"
      @click="boot"
    >
      重试读取
    </button>
    <template v-if="(!loading || mode === 'login') && !bootFailed">
      <form
        v-if="canSubmit"
        class="form-grid auth-form login-form"
        :aria-busy="busy"
        @submit.prevent="submit"
      >
        <label v-if="mode === 'login'" class="field field--wide"
          ><span class="field__label">账号名或邮箱</span
          ><input
            v-model="account"
            autocomplete="username"
            autocapitalize="none"
            :spellcheck="false"
            maxlength="254"
            required
            :disabled="busy || loading"
            placeholder="输入账号名或邮箱"
        /></label>
        <template v-if="mode === 'register'">
          <label class="field field--wide"
            ><span id="username-label" class="field__label">账号名</span
            ><input
              v-model="username"
              autocomplete="username"
              autocapitalize="none"
              :spellcheck="false"
              pattern="[A-Za-z][A-Za-z0-9_-]{2,31}"
              minlength="3"
              maxlength="32"
              required
              :disabled="busy || loading"
              aria-describedby="username-help"
              aria-labelledby="username-label"
            /><small id="username-help"
              >3–32位，以字母开头，可用数字、下划线和短横线。</small
            ></label
          >
          <label class="field field--wide"
            ><span class="field__label">昵称（选填）</span
            ><input
              v-model="nickname"
              autocomplete="nickname"
              maxlength="40"
              :disabled="busy || loading"
          /></label>
        </template>
        <label
          v-if="mode === 'register' || mode === 'forgot'"
          class="field field--wide"
          ><span class="field__label">邮箱</span
          ><input
            v-model="email"
            type="email"
            autocomplete="email"
            autocapitalize="none"
            :spellcheck="false"
            maxlength="254"
            required
            :disabled="busy || loading"
        /></label>
        <div v-if="hasPassword" class="login-password-group field--wide">
          <PasswordField
            v-model="password"
            :label="mode === 'reset' ? '新密码' : '密码'"
            :autocomplete="
              mode === 'login' ? 'current-password' : 'new-password'
            "
            :required="true"
            :disabled="busy || loading"
          />
          <router-link
            v-if="mode === 'login'"
            class="login-forgot"
            :to="withNext('/forgot-password')"
            >忘记密码</router-link
          >
          <small v-if="mode !== 'login'" class="gateway-muted"
            >使用12–128个字符。</small
          >
        </div>
        <PasswordField
          v-if="mode === 'register' || mode === 'reset'"
          v-model="confirmPassword"
          label="确认密码"
          autocomplete="new-password"
          :required="true"
          :disabled="busy || loading"
        />
        <label v-if="mode === 'login'" class="gateway-remember"
          ><input
            v-model="remember"
            type="checkbox"
            :disabled="busy || loading"
          /><span>记住登录30天</span></label
        >
        <label v-if="mode === 'verify'" class="field field--wide"
          ><span id="code-label" class="field__label">邮箱验证码</span
          ><input
            v-model="code"
            inputmode="numeric"
            autocomplete="one-time-code"
            pattern="[0-9]{6}"
            minlength="6"
            maxlength="6"
            required
            :disabled="busy || loading"
            aria-describedby="code-help"
            aria-labelledby="code-label"
          /><small id="code-help"
            >输入邮件中的六位数字，验证码10分钟内有效。</small
          ></label
        >
        <button
          v-press-feedback="'submit'"
          class="button login-submit action-submit field--wide"
          type="submit"
          :disabled="busy || loading"
        >
          {{ busy ? "正在处理…" : action }}
        </button>
      </form>
      <p
        v-if="mode === 'register' && !options.registrationOpen"
        class="gateway-muted"
        role="status"
      >
        注册暂未开放，请联系管理员。
      </p>
      <p
        v-if="mode === 'forgot' && !options.emailAvailable"
        class="gateway-muted"
        role="status"
      >
        邮件服务暂不可用，请联系管理员恢复账号。
      </p>
      <div v-if="mode === 'verify' && flow" class="login-secondary-nav">
        <button
          class="gateway-text-button"
          type="button"
          :disabled="busy || countdown > 0 || expired"
          @click="resend"
        >
          {{ countdown > 0 ? `${countdown}秒后可重发` : "重新发送验证码" }}
        </button>
      </div>
      <p v-if="expired" class="gateway-problem" role="status">
        验证已过期，请重新开始。
      </p>
      <nav class="login-invitation" aria-label="账号操作">
        <template v-if="mode === 'login'"
          ><span>还没有账号？</span
          ><router-link :to="withNext('/register')"
            >注册账号 <span aria-hidden="true">↗</span></router-link
          ></template
        >
        <template v-else-if="mode === 'verify' || mode === 'reset'"
          ><router-link
            :to="
              withNext(
                flow?.purpose === 'register' ? '/register' : '/forgot-password',
              )
            "
            >重新开始</router-link
          ><router-link :to="withNext('/login')"
            >返回登录</router-link
          ></template
        >
        <router-link v-else :to="withNext('/login')">返回登录</router-link>
      </nav>
    </template>
  </AuthFrame>
</template>
<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { safeContinue } from "../continueTarget";
import AuthFrame from "../components/AuthFrame.vue";
import PasswordField from "../components/PasswordField.vue";
import { api, ApiError } from "../api";
import { useSessionStore, type Session } from "../stores/session";
import { notify } from "../notifications";
type Flow = {
  purpose: "register" | "reset";
  stage: "verify" | "reset";
  emailHint: string;
  expiresAt: string;
  resendAt: string;
  next: string;
};
type Result = { session?: Session; next?: string; flow?: Flow; stage?: string };
type Mode = "login" | "register" | "forgot" | "verify" | "reset";
const route = useRoute(),
  router = useRouter(),
  session = useSessionStore();
const mode = route.meta.authMode as Mode;
const bootFailed = ref(false);
const loading = ref(true),
  busy = ref(false),
  error = ref(""),
  options = ref({ registrationOpen: false, emailAvailable: false });
const account = ref(""),
  username = ref(""),
  nickname = ref(""),
  email = ref(""),
  password = ref(""),
  confirmPassword = ref(""),
  code = ref(""),
  remember = ref(false);
const flow = ref<Flow | null>(null),
  clock = ref(Date.now());
let timer: ReturnType<typeof setInterval>;
let disposed = false;
const next = computed(
  () =>
    flow.value?.next ??
    (typeof route.query.next === "string" ? route.query.next : "/account"),
);
const withNext = (path: string) => ({ path, query: { next: next.value } });
const title = {
  login: "登录账号",
  register: "注册账号",
  forgot: "找回密码",
  verify: "验证邮箱",
  reset: "设置新密码",
}[mode];
const description = computed(() =>
  mode === "verify"
    ? flow.value
      ? `验证码已发送至 ${flow.value.emailHint}`
      : "没有可继续的验证流程，请重新开始。"
    : (
        {
          login: "一个账号，连接你的应用。",
          register: "创建账号，验证邮箱后即可使用。",
          forgot: "输入注册邮箱，继续验证身份。",
          reset: "设置新密码后，请重新登录。",
        } as Record<string, string>
      )[mode],
);
const action = {
  login: "登录",
  register: "发送验证码",
  forgot: "发送验证码",
  verify: "验证并继续",
  reset: "保存新密码",
}[mode];
const hasPassword = computed(() =>
  ["login", "register", "reset"].includes(mode),
);
const expired = computed(
  () => !!flow.value && Date.parse(flow.value.expiresAt) <= clock.value,
);
const countdown = computed(() =>
  flow.value
    ? Math.max(
        0,
        Math.ceil((Date.parse(flow.value.resendAt) - clock.value) / 1000),
      )
    : 0,
);
const canSubmit = computed(
  () =>
    !expired.value &&
    (mode === "register"
      ? options.value.registrationOpen
      : mode === "forgot"
        ? options.value.emailAvailable
        : mode === "verify"
          ? flow.value?.stage === "verify"
          : mode === "reset"
            ? flow.value?.stage === "reset"
            : true),
);
function showError(e: unknown) {
  error.value = e instanceof Error ? e.message : "请求未完成，请重试。";
}
async function boot() {
  bootFailed.value = false;
  loading.value = true;
  error.value = "";
  try {
    await session.refresh();
    if (disposed) return;
    if (session.user) {
      await router.replace(safeContinue(next.value));
      return;
    }
    if (mode === "register" || mode === "forgot")
      options.value = await api("/api/auth/options");
    if (mode === "verify" || mode === "reset") {
      flow.value = (await api<{ flow: Flow | null }>("/api/auth/flow")).flow;
      if (
        flow.value &&
        ((mode === "verify" && flow.value.stage === "reset") ||
          (mode === "reset" && flow.value.stage === "verify"))
      )
        await router.replace(
          flow.value.stage === "reset" ? "/reset-password" : "/verify-email",
        );
    }
  } catch (e) {
    if (disposed) return;
    bootFailed.value = true;
    showError(e);
  } finally {
    if (!disposed) loading.value = false;
  }
}
async function submit() {
  if (busy.value || loading.value || bootFailed.value || !canSubmit.value)
    return;
  error.value = "";
  if (
    (mode === "register" || mode === "reset") &&
    (password.value.length < 12 ||
      password.value.length > 128 ||
      password.value !== confirmPassword.value)
  ) {
    error.value = "密码须为12–128个字符，且两次输入一致。";
    return;
  }
  busy.value = true;
  try {
    const endpoint = {
      login: "login",
      register: "register",
      forgot: "forgot-password",
      verify: "verify-email",
      reset: "reset-password",
    }[mode];
    const body =
      mode === "login"
        ? {
            account: account.value,
            password: password.value,
            remember: remember.value,
            next: next.value,
          }
        : mode === "register"
          ? {
              username: username.value,
              nickname: nickname.value,
              email: email.value,
              password: password.value,
              confirmPassword: confirmPassword.value,
              next: next.value,
            }
          : mode === "forgot"
            ? { email: email.value, next: next.value }
            : mode === "verify"
              ? { code: code.value }
              : {
                  password: password.value,
                  confirmPassword: confirmPassword.value,
                };
    const result = await session.mutate<Result>(`/api/auth/${endpoint}`, body);
    if (disposed) return;
    if (result.session) session.accept(result.session);
    password.value = "";
    confirmPassword.value = "";
    code.value = "";
    if (mode === "reset") {
      notify("密码已更新，请重新登录。", "success");
      await router.replace({
        path: "/login",
        query: { next: result.next ?? "/account" },
      });
    } else if (result.session) {
      await router.replace(result.next ?? "/account");
    } else if (result.stage === "reset")
      await router.replace("/reset-password");
    else await router.push("/verify-email");
  } catch (e) {
    if (disposed) return;
    showError(e);
    code.value = "";
    if (e instanceof ApiError && e.code === "csrf_failed") {
      await session.refresh().catch(() => undefined);
      error.value = "会话已刷新，请重新提交。";
    }
  } finally {
    busy.value = false;
  }
}
async function resend() {
  if (busy.value || countdown.value || expired.value) return;
  busy.value = true;
  error.value = "";
  try {
    const result = await session.mutate<{ flow: Flow }>("/api/auth/resend");
    flow.value = result.flow;
    code.value = "";
    notify("验证码已重新发送。", "success");
  } catch (e) {
    if (disposed) return;
    showError(e);
  } finally {
    busy.value = false;
  }
}
onMounted(() => {
  void boot();
  timer = setInterval(() => {
    clock.value = Date.now();
  }, 1000);
});
onBeforeUnmount(() => {
  disposed = true;
  clearInterval(timer);
  password.value = "";
  confirmPassword.value = "";
  code.value = "";
});
</script>
