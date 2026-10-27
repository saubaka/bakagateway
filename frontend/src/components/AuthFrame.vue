<template>
  <div class="login-page">
    <main id="main-content" class="login-main" tabindex="-1">
      <section
        v-motion="{ kind: 'feature', reversible: false }"
        class="login-card card"
        aria-labelledby="auth-title"
      >
        <header class="login-heading">
          <span class="login-logo" aria-hidden="true"
            ><svg viewBox="0 0 40 40" fill="none">
              <rect x="9" y="9" width="9" height="21" rx="4.5" />
              <rect x="22" y="11" width="9" height="21" rx="4.5" /></svg
          ></span>
          <span class="login-product-name">{{ siteInfo.siteName }}</span>
          <h1 id="auth-title">{{ title }}</h1>
          <p>{{ description }}</p>
        </header>
        <slot />
      </section>
    </main>
    <footer class="login-footer">
      <p v-if="siteInfo.supportEmail" class="gateway-muted">
        <a :href="`mailto:${siteInfo.supportEmail}`">联系支持</a>
      </p>

      <p>{{ siteInfo.description }}</p>
      <p>© {{ new Date().getFullYear() }} saubaka · baka</p>
    </footer>
  </div>
</template>
<script setup lang="ts">
import { siteInfo } from "../siteInfo";
defineProps<{ title: string; description: string }>();
</script>
