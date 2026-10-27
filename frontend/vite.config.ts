import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

const target = process.env.BG_API_PROXY ?? "http://127.0.0.1:5180";
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5181,
    strictPort: true,
    proxy: {
      "/api": { target, headers: { "X-Forwarded-For": "127.0.0.1" } },
      "/oauth": { target },
      "/.well-known": { target },
    },
  },
  build: { sourcemap: false },
});
