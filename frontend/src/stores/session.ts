import { defineStore } from "pinia";
import { ref } from "vue";
import { api } from "../api";
export type User = {
  id: string;
  username: string;
  nickname: string;
  email: string;
  emailVerified: boolean;
  avatarUrl: string | null;
  role: "user" | "admin";
};
export type Session = {
  authenticated: boolean;
  user: User | null;
  csrfToken: string;
};
export const useSessionStore = defineStore("session", () => {
  const csrfToken = ref("");
  const user = ref<User | null>(null);
  let generation = 0;
  function accept(value: Session) {
    generation++;
    csrfToken.value = value.csrfToken;
    user.value = value.user;
  }
  async function refresh() {
    const started = generation;
    const value = await api<Session>("/api/auth/session");
    if (started === generation) accept(value);
    return {
      authenticated: !!user.value,
      user: user.value,
      csrfToken: csrfToken.value,
    };
  }
  function updateUser(value: User) {
    if (user.value?.id === value.id) {
      generation++;
      user.value = value;
    }
  }
  function invalidate() {
    generation++;
    user.value = null;
    csrfToken.value = "";
  }
  async function mutate<T>(path: string, body: unknown = {}) {
    if (!csrfToken.value) await refresh();
    return api<T>(path, { method: "POST", csrfToken: csrfToken.value, body });
  }
  return { csrfToken, user, accept, updateUser, invalidate, refresh, mutate };
});
