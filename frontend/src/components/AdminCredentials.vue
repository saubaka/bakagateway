<template>
  <section
    class="managed-page-card admin-credentials"
    aria-labelledby="credential-title"
  >
    <h2 id="credential-title">保存接入密钥</h2>
    <p>仅此一次展示，关闭后无法再次查看。请安全交给接入网站的后端维护者。</p>
    <label class="field"
      ><span>应用标识</span
      ><input :value="value.clientId" readonly autocomplete="off" /></label
    ><label class="field"
      ><span>应用密钥</span
      ><textarea
        :value="value.clientSecret"
        readonly
        rows="3"
        autocomplete="off"
        spellcheck="false"
      />
    </label>
    <div class="button-row">
      <button class="button button--soft" @click="copy">复制凭据</button
      ><button class="button button--soft" @click="download">下载凭据</button
      ><button class="button button--primary" @click="$emit('close')">
        已保存，关闭
      </button>
    </div>
    <p class="gateway-muted">
      接入方式：发现地址为本站
      /.well-known/openid-configuration，使用授权码与S256；密钥只保存在应用后端。
    </p>
  </section>
</template>
<script setup lang="ts">
import type { Credentials } from "../admin";
import { notify } from "../notifications";
const p = defineProps<{ value: Credentials }>();
defineEmits<{ close: [] }>();
const content = () =>
  JSON.stringify(
    { client_id: p.value.clientId, client_secret: p.value.clientSecret },
    null,
    2,
  );
async function copy() {
  try {
    await navigator.clipboard.writeText(content());
    notify("凭据已复制，请安全保管。");
  } catch {
    notify("未能复制，请手动选择或下载。", "error");
  }
}
function download() {
  const url = URL.createObjectURL(
    new Blob([content()], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = "application-credentials.json";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
</script>
