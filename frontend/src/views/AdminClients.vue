<template>
  <div v-admin-entrance class="admin-route-panel account-page">
    <AdminCredentials
      v-if="credentials"
      :value="credentials"
      @close="credentials = undefined"
    />
    <section class="managed-page-card">
      <header class="panel-heading">
        <div>
          <h2>{{ editing ? "编辑应用" : "登记应用" }}</h2>
          <p>
            供有自己后端的网站接入。编辑、停用、换图标或轮换密钥会撤销旧凭据。
          </p>
        </div>
        <button
          v-if="editing"
          class="button button--soft"
          :disabled="busy"
          @click="reset"
        >
          取消编辑
        </button>
      </header>
      <form class="form-stack" @submit.prevent="save">
        <fieldset :disabled="busy">
          <div class="admin-edit-grid">
            <label class="field"
              ><span>应用名称</span
              ><input
                ref="nameInput"
                v-model="form.name"
                required
                maxlength="80" /></label
            ><label class="field"
              ><span>应用主页（可选）</span
              ><input
                v-model="form.homepage"
                type="url"
                maxlength="512" /></label
            ><label class="field admin-wide"
              ><span>应用介绍</span
              ><textarea
                v-model="form.description"
                maxlength="240"
                rows="2"
              /></label
            ><label class="field admin-wide"
              ><span>登录返回地址（每行一个，最多10个）</span
              ><textarea
                v-model="redirects"
                required
                rows="3"
                placeholder="https://app.example/callback"
                spellcheck="false"
              /></label
            ><label class="field"
              ><span>隐私说明地址（可选）</span
              ><input
                v-model="form.privacyUrl"
                type="url"
                maxlength="512" /></label
            ><label class="field"
              ><span>服务条款地址（可选）</span
              ><input v-model="form.termsUrl" type="url" maxlength="512"
            /></label>
            <fieldset class="admin-wide admin-scopes">
              <legend>允许申请的资料</legend>
              <label v-for="(label, key) in scopeLabels" :key="key"
                ><input
                  v-model="form.scopes"
                  type="checkbox"
                  :value="key"
                  :disabled="key === 'openid'"
                />
                {{ label }}</label
              >
            </fieldset>
            <label class="admin-check"
              ><input v-model="form.active" type="checkbox" />启用应用</label
            >
          </div>
        </fieldset>
        <div class="button-row">
          <button
            class="button button--primary"
            :disabled="busy || !!credentials"
          >
            {{ busy ? "正在处理…" : editing ? "保存应用" : "登记并生成密钥" }}
          </button>
        </div>
      </form>
      <p v-if="credentials" class="gateway-muted">请先保存并关闭上方凭据。</p>
    </section>
    <section class="managed-page-card">
      <header class="panel-heading">
        <h2>接入应用</h2>
        <button class="button button--soft" :disabled="busy" @click="load">
          刷新
        </button>
      </header>
      <form class="admin-search" @submit.prevent="search">
        <label class="field"
          ><span>搜索应用</span
          ><input
            v-model="query"
            maxlength="80"
            placeholder="名称或应用标识"
            :disabled="busy" /></label
        ><label class="field"
          ><span>应用状态</span
          ><select v-model="status" :disabled="busy">
            <option value="all">全部状态</option>
            <option value="active">启用</option>
            <option value="inactive">停用</option>
          </select></label
        ><button class="button button--soft" :disabled="busy">筛选</button>
      </form>
      <AccountFeedback :error="error" />
      <p v-if="busy" role="status">正在处理…</p>
      <div v-if="data" class="admin-list">
        <article v-for="row in data.items" :key="row.id" class="admin-list-row">
          <div>
            <div class="admin-client-heading">
              <img
                v-if="row.iconUrl && row.active"
                :src="row.iconUrl"
                class="admin-app-icon"
                alt=""
              />
              <h3>{{ row.name }}</h3>
            </div>
            <p>{{ row.description || "未填写介绍" }}</p>
            <p class="gateway-muted">
              {{ row.active ? "启用" : "停用" }} · {{ row.id }}
            </p>
            <p class="gateway-muted">
              {{ row.scopes.map((s) => scopeLabels[s]).join("、") }}
            </p>
            <details>
              <summary>返回地址与接入说明</summary>
              <ul>
                <li v-for="url in row.redirectUris" :key="url">{{ url }}</li>
              </ul>
              <p>
                使用本站发现地址与client_secret_basic，在应用后端交换凭据；浏览器端使用S256。
              </p>
            </details>
          </div>
          <div class="button-row">
            <button
              class="button button--soft"
              :disabled="busy"
              :aria-label="`编辑 ${row.name}`"
              @click="edit(row)"
            >
              编辑</button
            ><button
              class="button button--soft"
              :disabled="busy"
              :aria-label="`${row.active ? '停用' : '启用'} ${row.name}`"
              @click="toggle(row)"
            >
              {{ row.active ? "停用" : "启用" }}</button
            ><button
              class="button button--soft"
              :disabled="busy || !!credentials"
              :aria-label="`轮换密钥：${row.name}`"
              @click="rotate(row)"
            >
              轮换密钥</button
            ><label
              class="button button--soft admin-file"
              :class="{ 'is-disabled': busy }"
              >更换图标<input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                :aria-label="`更换 ${row.name} 的图标`"
                :disabled="busy"
                @change="icon($event, row)" /></label
            ><button
              v-if="row.iconUrl"
              class="button button--soft"
              :disabled="busy"
              @click="removeIcon(row)"
            >
              移除图标
            </button>
          </div>
        </article>
        <p v-if="!data.items.length" class="gateway-muted">
          没有符合条件的应用。
        </p>
        <AdminPager v-bind="data" :busy="busy" @change="go" />
      </div>
    </section>
  </div>
</template>
<script setup lang="ts">
import { ref, reactive, onMounted, nextTick } from "vue";
import { api } from "../api";
import { useAccountTask } from "../account";
import {
  adminWrite,
  scopeLabels,
  type Page,
  type Client,
  type Credentials,
} from "../admin";
import AccountFeedback from "../components/AccountFeedback.vue";
import AdminPager from "../components/AdminPager.vue";
import AdminCredentials from "../components/AdminCredentials.vue";
import { notify } from "../notifications";
import { adminEntranceDirective as vAdminEntrance } from "../admin/entrance";
const { busy, error, run, isActive } = useAccountTask();
const data = ref<Page<Client>>(),
  credentials = ref<Credentials>(),
  query = ref(""),
  status = ref("all"),
  page = ref(1),
  editing = ref<Client>(),
  redirects = ref(""),
  nameInput = ref<HTMLInputElement>();
let applied = { q: "", status: "all" };
const empty = () => ({
  name: "",
  description: "",
  homepage: "",
  privacyUrl: "",
  termsUrl: "",
  scopes: ["openid", "profile", "email"],
  active: true,
});
const form = reactive(empty());
function reset() {
  editing.value = undefined;
  Object.assign(form, empty());
  redirects.value = "";
}
async function fetchRows() {
  const value = await api<Page<Client>>(
    "/api/admin/clients?" +
      new URLSearchParams({ ...applied, page: String(page.value) }),
  );
  if (isActive()) data.value = value;
}
async function load() {
  await run(fetchRows);
}
function search() {
  applied = { q: query.value, status: status.value };
  page.value = 1;
  void load();
}
function go(n: number) {
  page.value = n;
  void load();
}
async function edit(row: Client) {
  editing.value = {
    ...row,
    scopes: [...row.scopes],
    redirectUris: [...row.redirectUris],
  };
  Object.assign(form, { ...row, scopes: [...row.scopes] });
  redirects.value = row.redirectUris.join("\n");
  await nextTick();
  nameInput.value?.focus();
  nameInput.value?.scrollIntoView({ block: "center", behavior: "auto" });
}
function body() {
  return {
    name: form.name,
    description: form.description,
    homepage: form.homepage,
    privacyUrl: form.privacyUrl,
    termsUrl: form.termsUrl,
    scopes: [...form.scopes],
    active: form.active,
    redirectUris: redirects.value
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean),
  };
}
async function save() {
  await run(async () => {
    const selected = editing.value;
    const v = await adminWrite<{ client: Client; credentials?: Credentials }>(
      selected ? `/api/admin/clients/${selected.id}` : "/api/admin/clients",
      { ...body(), ...(selected ? { expectedVersion: selected.version } : {}) },
      selected
        ? "保存应用并撤销其旧凭据。"
        : "登记新应用并仅显示一次接入密钥。",
    );
    if (!v || !isActive()) return;
    credentials.value = v.credentials;
    reset();
    await fetchRows();
    notify("应用已保存。");
  });
}
async function toggle(row: Client) {
  await run(async () => {
    const { id, version, iconUrl, createdAt, ...body } = row;
    const v = await adminWrite(
      `/api/admin/clients/${id}`,
      { ...body, active: !row.active, expectedVersion: version },
      `${row.active ? "停用" : "启用"} ${row.name}，旧凭据将被撤销。`,
    );
    if (v) {
      await fetchRows();
      notify("应用状态已更新。");
    }
  });
}
async function rotate(row: Client) {
  await run(async () => {
    const v = await adminWrite<{ credentials: Credentials }>(
      `/api/admin/clients/${row.id}/rotate`,
      { expectedVersion: row.version },
      `轮换 ${row.name} 的密钥并撤销旧凭据。接入网站必须更新密钥。`,
    );
    if (v && isActive()) {
      credentials.value = v.credentials;
      await fetchRows();
      notify("密钥已轮换，请立即保存。");
    }
  });
}
async function icon(event: Event, row: Client) {
  const input = event.target as HTMLInputElement,
    file = input.files?.[0];
  if (!file) return;
  await run(async () => {
    try {
      if (file.size > 2 * 1024 * 1024) throw new Error("图标不能超过2MiB。");
      const encoded = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(",")[1]);
        reader.onerror = () => reject(new Error("无法读取图片。"));
        reader.readAsDataURL(file);
      });
      if (!isActive()) return;
      const v = await adminWrite(
        `/api/admin/clients/${row.id}/icon`,
        { image: encoded, expectedVersion: row.version },
        "保存清洗后的应用图标，并撤销旧凭据。",
      );
      if (v) {
        await fetchRows();
        notify("图标已更新。");
      }
    } finally {
      input.value = "";
    }
  });
}
async function removeIcon(row: Client) {
  await run(async () => {
    const v = await adminWrite(
      `/api/admin/clients/${row.id}/icon`,
      { image: null, expectedVersion: row.version },
      "移除应用图标并撤销旧凭据。",
    );
    if (v) await fetchRows();
  });
}
onMounted(load);
</script>
