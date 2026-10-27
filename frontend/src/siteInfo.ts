import { reactive } from "vue";
import { api } from "./api";
export const siteInfo = reactive({
  siteName: "baka 身份平台",
  description: "一个账号，连接你的应用。",
  supportEmail: "",
});
export async function refreshSite() {
  const data = await api<{
    name: string;
    description: string;
    supportEmail: string;
  }>("/api/system");
  Object.assign(siteInfo, {
    siteName: data.name,
    description: data.description,
    supportEmail: data.supportEmail,
  });
}
