// Navigation convenience only; backend safe_next remains the authority.
export function safeContinue(value: unknown): string {
  if (typeof value !== "string" || value.length > 512) return "/account";
  let decoded: string;
  try {
    decoded = decodeURIComponent(decodeURIComponent(value));
  } catch {
    return "/account";
  }
  if (
    !decoded.startsWith("/") ||
    decoded.startsWith("//") ||
    /[\\\u0000-\u001f]/.test(decoded)
  )
    return "/account";
  const url = new URL(decoded, "https://navigation.invalid");
  if (url.origin !== "https://navigation.invalid" || url.hash)
    return "/account";
  const path = url.pathname;
  const valid =
    path === "/account" ||
    path.startsWith("/account/") ||
    [
      "/admin",
      "/admin/users",
      "/admin/clients",
      "/admin/mail",
      "/admin/settings",
      "/admin/audit",
    ].includes(path) ||
    (path === "/authorize" &&
      /^[A-Za-z0-9_-]{16,128}$/.test(url.searchParams.get("tx") ?? ""));
  return valid ? path + url.search : "/account";
}
