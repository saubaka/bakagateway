import { promptDialog } from "./dialog";
import { useSessionStore } from "./stores/session";
export type Page<T> = {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
};
export type AdminUser = {
  id: string;
  username: string;
  nickname: string;
  email: string;
  role: "admin" | "user";
  active: boolean;
  version: number;
  createdAt: string;
};
export type Client = {
  id: string;
  name: string;
  description: string;
  homepage: string;
  privacyUrl: string;
  termsUrl: string;
  redirectUris: string[];
  scopes: string[];
  active: boolean;
  version: number;
  iconUrl: string | null;
  createdAt: string;
};
export type Credentials = { clientId: string; clientSecret: string };
export type Audit = {
  id: string;
  actorId: string;
  actorName: string;
  action: string;
  targetId: string;
  summary: string;
  createdAt: string;
};
export const scopeLabels: Record<string, string> = {
  openid: "基础身份（必需）",
  profile: "昵称、账号名与头像",
  email: "邮箱",
  offline_access: "保持应用连接",
};
export async function adminWrite<T>(
  path: string,
  body: object,
  message: string,
): Promise<T | undefined> {
  const password = await promptDialog({
    title: "确认管理操作",
    message,
    fieldLabel: "当前密码",
    inputType: "password",
    confirmLabel: "确认并提交",
    validate: (v) => (v.length > 128 ? "密码过长。" : ""),
  });
  if (password === null) return;
  return useSessionStore().mutate<T>(path, {
    ...body,
    currentPassword: password,
  });
}
export const actionLabels: Record<string, string> = {
  "user.update": "修改用户",
  "client.create": "登记应用",
  "client.update": "修改应用",
  "client.rotate": "轮换密钥",
  "client.icon": "修改图标",
  "settings.update": "更新站点",
  "mail.update": "更新邮件",
  "mail.test": "测试发信",
};
