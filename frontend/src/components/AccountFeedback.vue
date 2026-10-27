<template>
  <p v-if="loading" class="gateway-muted" role="status">正在读取…</p>
  <p
    v-if="error"
    ref="alert"
    class="gateway-problem"
    role="alert"
    tabindex="-1"
  >
    {{ error }}
  </p>
</template>
<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
const props = defineProps<{ loading?: boolean; error: string }>();
const alert = ref<HTMLElement | null>(null);
watch(
  () => props.error,
  async (value) => {
    if (value) {
      await nextTick();
      alert.value?.focus();
    }
  },
);
</script>
