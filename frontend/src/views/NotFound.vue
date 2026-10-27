<template>
  <main id="main-content" class="gateway-not-found" tabindex="-1">
    <section class="card" v-motion>
      <span class="eyebrow">404</span>
      <h1>页面不存在</h1>
      <p>这个地址暂时没有可访问的页面。</p>
      <router-link class="button button--primary" to="/login"
        >返回登录</router-link
      >
    </section>
  </main>
</template>
