import { ref, onBeforeUnmount } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ApiError } from "./api";
import { useSessionStore } from "./stores/session";
export function useAccountTask() {
  const busy = ref(false),
    error = ref("");
  const session = useSessionStore(),
    router = useRouter(),
    route = useRoute();
  let active = true;
  onBeforeUnmount(() => {
    active = false;
  });
  async function run<T>(work: () => Promise<T>): Promise<T | undefined> {
    if (busy.value || !active) return;
    busy.value = true;
    error.value = "";
    try {
      return await work();
    } catch (e) {
      if (!active) return;
      if (e instanceof ApiError && e.code === "admin_required") {
        await session.refresh().catch(() => undefined);
        await router.replace("/forbidden");
        return;
      }
      if (e instanceof ApiError && e.code === "authentication_required") {
        session.invalidate();
        await router.replace({
          path: "/login",
          query: { next: route.fullPath },
        });
        return;
      }
      error.value = e instanceof Error ? e.message : "操作未完成，请重试。";
      if (e instanceof ApiError && e.code === "csrf_failed") {
        try {
          await session.refresh();
        } catch {
          error.value = "暂时无法刷新会话，请稍后重试。";
          return;
        }
        if (!session.user) {
          await router.replace({
            path: "/login",
            query: { next: route.fullPath },
          });
          return;
        }
        error.value = "会话已刷新，请重新提交。";
      }
    } finally {
      if (active) busy.value = false;
    }
  }
  return { busy, error, run, isActive: () => active };
}
export const dateLabel = (value: string) =>
  new Date(value).toLocaleString("zh-CN", { hour12: false });
export type EmailFlow = {
  purpose: "email-change";
  stage: "verify";
  emailHint: string;
  expiresAt: string;
  resendAt: string;
  next: string;
};
export type Device = {
  id: string;
  label: string;
  ipAddress: string;
  createdAt: string;
  lastSeenAt: string;
  expiresAt: string;
  current: boolean;
};
