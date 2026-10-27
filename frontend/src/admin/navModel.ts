export type IconName =
  | "overview" | "accounts" | "invites" | "ops" | "security" | "human" | "admins" | "system" | "seo"
  | "logout" | "mail" | "search" | "panel" | "return"
  | "send" | "alert" | "clock" | "unread" | "chevron";

export type RailBadgeKey = "accounts" | "security";

export type RailItem = {
  name: string;
  label: string;
  icon: IconName;
  permission: string;
  section: "main" | "mail" | "ops" | "security" | "system";
  keywords: string;
  shortcut: string;
  badge?: RailBadgeKey;
};


export type RailSection = { key: RailItem["section"]; label: string; items: RailItem[] };
