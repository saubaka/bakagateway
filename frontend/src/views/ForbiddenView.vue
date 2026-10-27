<template>
  <AuthFrame title="无权访问" description="这个页面仅向平台管理员开放。"
    ><router-link class="button button--primary" to="/account"
      >返回个人中心</router-link
    ></AuthFrame
  >
</template>
<script setup lang="ts">
import AuthFrame from "../components/AuthFrame.vue";
</script>
