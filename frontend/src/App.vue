<template>
  <router-view v-slot="{ Component, route }">
    <transition name="baka-route" mode="out-in" @after-enter="focusMain">
      <component
        :is="Component"
        :key="
          route.path === '/authorize'
            ? route.fullPath
            : (route.matched[0]?.path ?? route.path)
        "
      />
    </transition>
  </router-view>
  <BakaDialog />
</template>
<script setup lang="ts">
import { onMounted, watch } from "vue";
import { useRoute } from "vue-router";
import { siteInfo, refreshSite } from "./siteInfo";
import { dialogState, settleDialog } from "./dialog";
import BakaDialog from "./components/BakaDialog.vue";
const route = useRoute();
watch(
  () => route.fullPath,
  () => {
    if (dialogState.open) settleDialog(null);
  },
);
onMounted(() => {
  void refreshSite().catch(() => undefined);
});
watch(
  () => siteInfo.siteName,
  () => {
    document.title = `${route.meta.title ?? "baka"} · ${siteInfo.siteName}`;
  },
);
function focusMain() {
  document.getElementById("main-content")?.focus({ preventScroll: true });
}
</script>
