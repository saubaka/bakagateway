<template>
  <AuthFrame
    title="服务暂时不可用"
    description="暂时无法确认连接状态。已有登录不会因此被当作退出，请稍后重试。"
    ><p v-if="error" class="gateway-problem" role="alert">{{ error }}</p>
    <div class="button-row">
      <button class="button button--primary" :disabled="busy" @click="retry">
        {{ busy ? "正在重试…" : "重新连接" }}</button
      ><router-link class="button button--soft" to="/login"
        >返回登录页</router-link
      >
    </div></AuthFrame
  >
</template>
<script setup lang="ts">
import { ref, onBeforeUnmount } from "vue";
import { useRoute, useRouter } from "vue-router";
import AuthFrame from "../components/AuthFrame.vue";
import { useSessionStore } from "../stores/session";
import { safeContinue } from "../continueTarget";
const route = useRoute(),
  router = useRouter(),
  session = useSessionStore();
const busy = ref(false),
  error = ref("");
let active = true;
onBeforeUnmount(() => {
  active = false;
});
async function retry() {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    const state = await session.refresh();
    if (!active) return;
    const next = safeContinue(route.query.next);
    await router.replace(
      state.authenticated ? next : { path: "/login", query: { next } },
    );
  } catch (e) {
    if (active)
      error.value = e instanceof Error ? e.message : "连接未恢复，请稍后重试。";
  } finally {
    if (active) busy.value = false;
  }
}
</script>
