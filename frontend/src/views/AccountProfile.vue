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
            <h2>头像</h2>
            <p>选择后自动保存，支持PNG、JPEG和静态WebP，最多2MiB。</p>
          </div>
        </header>
        <div class="account-avatar-editor">
          <span class="avatar account-avatar" aria-hidden="true"
            ><img
              v-if="session.user?.avatarUrl"
              :src="session.user.avatarUrl"
              alt=""
            /><template v-else>{{
              session.user?.nickname.slice(0, 1)
            }}</template></span
          >
          <label class="field"
            ><span class="field__label">选择头像</span
            ><input
              type="file"
              accept="image/png,image/jpeg,image/webp"
              :disabled="busy"
              @change="upload"
          /></label>
          <button
            v-if="session.user?.avatarUrl"
            class="button button--soft"
            :disabled="busy"
            @click="remove"
          >
            移除头像
          </button>
        </div>
      </section>
      <section class="managed-page-card">
        <header class="panel-heading">
          <div>
            <h2>基本资料</h2>
            <p>昵称可以修改，账号名与身份编号保持不变。</p>
          </div>
        </header>
        <form
          class="form-stack account-form"
          :aria-busy="busy"
          @submit.prevent="save"
        >
          <label class="field"
            ><span class="field__label">昵称</span
            ><input
              v-model="nickname"
              autocomplete="nickname"
              maxlength="40"
              required
              :disabled="busy"
          /></label>
          <div class="button-row">
            <button
              class="button button--primary"
              type="submit"
              :disabled="busy || nickname === session.user?.nickname"
            >
              {{ busy ? "正在保存…" : "保存资料" }}
            </button>
          </div>
        </form>
        <dl class="detail-grid account-identity">
          <div>
            <dt>账号名</dt>
            <dd>{{ session.user?.username }}</dd>
          </div>
          <div>
            <dt>身份编号</dt>
            <dd>{{ session.user?.id }}</dd>
          </div>
        </dl>
      </section>
    </template>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from "vue";
import { api } from "../api";
import { useSessionStore, type User } from "../stores/session";
import { useAccountTask } from "../account";
import AccountFeedback from "../components/AccountFeedback.vue";
import { adminEntranceDirective as vAdminEntrance } from "../admin/entrance";
import { notify } from "../notifications";
const session = useSessionStore(),
  { busy, error, run, isActive } = useAccountTask(),
  loaded = ref(false),
  nickname = ref("");
async function load() {
  await run(async () => {
    const result = await api<{ user: User }>("/api/account/profile");
    session.updateUser(result.user);
    nickname.value = result.user.nickname;
    loaded.value = true;
    return true;
  });
}
async function save() {
  const result = await run(() =>
    session.mutate<{ user: User }>("/api/account/profile", {
      nickname: nickname.value,
    }),
  );
  if (result) {
    session.updateUser(result.user);
    nickname.value = result.user.nickname;
    if (isActive()) notify("资料已保存。", "success");
  }
}
async function upload(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  if (file.size > 2 * 1024 * 1024) {
    error.value = "头像文件不能超过2MiB。";
    return;
  }
  const result = await run(async () => {
    const value = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
      reader.onerror = () => reject(new Error("无法读取图片，请重新选择。"));
      reader.readAsDataURL(file);
    });
    if (!isActive()) throw new Error("页面已切换，请重新选择头像。");
    return session.mutate<{ user: User }>("/api/account/avatar", {
      image: value,
    });
  });
  if (result) {
    session.updateUser(result.user);
    if (isActive()) notify("头像已更新。", "success");
  }
}
async function remove() {
  const result = await run(() =>
    session.mutate<{ user: User }>("/api/account/avatar/remove"),
  );
  if (result) {
    session.updateUser(result.user);
    if (isActive()) notify("头像已移除。", "success");
  }
}
onMounted(() => void load());
</script>
