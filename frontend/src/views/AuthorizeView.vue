<template>
  <AuthFrame title="登录应用" description="确认要分享的账号信息。">
    <p v-if="loading" class="gateway-muted" role="status">正在读取登录请求…</p>
    <p v-if="error" class="gateway-problem" role="alert">{{ error }}</p>
    <template v-if="data">
      <div class="consent-app">
        <img
          v-if="data.application.iconUrl"
          :src="data.application.iconUrl"
          class="admin-app-icon"
          alt=""
        />
        <h2>{{ data.application.name }}</h2>
        <p v-if="data.application.description">
          {{ data.application.description }}
        </p>
        <p class="gateway-muted">返回至 {{ data.application.returnHost }}</p>
      </div>
      <p class="gateway-muted consent-owner">
        正在使用 {{ data.user.nickname }}（{{ data.user.username }}）
      </p>
      <form class="form-stack" :aria-busy="busy" @submit.prevent="submit(true)">
        <label v-for="scope in data.scopes" :key="scope" class="consent-scope"
          ><input
            v-model="selected"
            type="checkbox"
            :value="scope"
            :disabled="busy || scope === 'openid'"
            :aria-labelledby="`scope-${scope}`"
          /><span
            ><strong :id="`scope-${scope}`">{{
              labels[scope]?.[0] ?? scope
            }}</strong
            ><small>{{ labels[scope]?.[1] }}</small></span
          ></label
        >
        <div class="button-row consent-actions">
          <button
            class="button button--soft"
            type="button"
            :disabled="busy"
            @click="submit(false)"
          >
            取消</button
          ><button
            class="button button--primary"
            type="submit"
            :disabled="busy"
          >
            {{ busy ? "正在返回…" : "同意并继续" }}
          </button>
        </div>
      </form>
      <nav class="login-secondary-nav" aria-label="应用说明">
        <a
          v-if="data.application.homepage"
          :href="data.application.homepage"
          target="_blank"
          rel="noopener noreferrer"
          >应用主页</a
        ><a
          v-if="data.application.privacyUrl"
          :href="data.application.privacyUrl"
          target="_blank"
          rel="noopener noreferrer"
          >隐私说明</a
        ><a
          v-if="data.application.termsUrl"
          :href="data.application.termsUrl"
          target="_blank"
          rel="noopener noreferrer"
          >使用条款</a
        >
      </nav>
    </template>
    <div v-else-if="!loading" class="login-secondary-nav">
      <button class="gateway-text-button" type="button" @click="load">
        重试读取</button
      ><router-link to="/account">返回个人中心</router-link>
    </div>
  </AuthFrame>
</template>
<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from "vue";
import { useRoute, useRouter } from "vue-router";
import AuthFrame from "../components/AuthFrame.vue";
import { api, ApiError } from "../api";
import { useSessionStore } from "../stores/session";
type Consent = {
  application: {
    name: string;
    iconUrl: string | null;
    description: string;
    homepage: string;
    privacyUrl: string;
    termsUrl: string;
    returnHost: string;
  };
  scopes: string[];
  user: { nickname: string; username: string };
  expiresAt: string;
};
const route = useRoute(),
  router = useRouter(),
  session = useSessionStore(),
  data = ref<Consent | null>(null),
  selected = ref<string[]>([]),
  error = ref(""),
  loading = ref(true),
  busy = ref(false);
const labels: Record<string, string[]> = {
  openid: ["基础身份（必需）", "使用稳定身份编号完成登录。"],
  profile: ["昵称、账号名与头像", "让应用显示你的称呼和头像。"],
  email: ["邮箱", "分享邮箱地址及验证状态。"],
  offline_access: [
    "保持应用连接",
    "允许应用在你离开平台后继续更新登录凭据，直到你撤销连接。",
  ],
};
const reference = typeof route.query.tx === "string" ? route.query.tx : "";
const abort = new AbortController();
async function handle(e: unknown) {
  if (abort.signal.aborted) return;
  error.value = e instanceof Error ? e.message : "登录请求暂时不可用。";
  if (e instanceof ApiError && e.code === "authentication_required")
    await router.replace({ path: "/login", query: { next: route.fullPath } });
  if (e instanceof ApiError && e.code === "csrf_failed")
    await session.refresh().catch(() => undefined);
}
async function load() {
  loading.value = true;
  data.value = null;
  error.value = "";
  try {
    data.value = await api(
      "/api/oauth/consent?tx=" + encodeURIComponent(reference),
      { signal: abort.signal },
    );
    selected.value = [...data.value!.scopes];
  } catch (e) {
    if (!abort.signal.aborted) await handle(e);
  } finally {
    loading.value = false;
  }
}
async function submit(approve: boolean) {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    const result = await session.mutate<{ redirectTo: string }>(
      "/api/oauth/consent",
      { tx: reference, approve, scopes: selected.value },
    );
    if (!abort.signal.aborted) window.location.assign(result.redirectTo);
  } catch (e) {
    await handle(e);
    busy.value = false;
  }
}
onMounted(() => void load());
onBeforeUnmount(() => abort.abort());
</script>
