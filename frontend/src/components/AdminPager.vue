<template>
  <nav class="admin-pager" aria-label="列表分页">
    <span role="status"
      >共 {{ total }} 项 · 第 {{ page }} / {{ pages }} 页</span
    >
    <div class="button-row">
      <button
        class="button button--soft"
        :disabled="busy || page <= 1"
        @click="$emit('change', page - 1)"
      >
        上一页</button
      ><button
        class="button button--soft"
        :disabled="busy || page >= pages"
        @click="$emit('change', page + 1)"
      >
        下一页
      </button>
    </div>
  </nav>
</template>
<script setup lang="ts">
import { computed } from "vue";
const p = defineProps<{
  total: number;
  page: number;
  pageSize: number;
  busy: boolean;
}>();
const pages = computed(() => Math.max(1, Math.ceil(p.total / p.pageSize)));
defineEmits<{ change: [page: number] }>();
</script>
