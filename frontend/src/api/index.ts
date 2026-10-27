export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
type Envelope<T> =
  | { ok: true; data: T; requestId: string }
  | { ok: false; error: { code: string; message: string }; requestId: string };

export async function api<T>(
  path: string,
  options: {
    method?: string;
    csrfToken?: string;
    signal?: AbortSignal;
    body?: unknown;
  } = {},
): Promise<T> {
  const method = options.method ?? "GET";
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      credentials: "same-origin",
      cache: "no-store",
      redirect: "error",
      signal: options.signal,
      headers: {
        ...(method === "POST" ? { "Content-Type": "application/json" } : {}),
        ...(options.csrfToken ? { "X-CSRF-Token": options.csrfToken } : {}),
      },
      ...(method === "POST"
        ? { body: JSON.stringify(options.body ?? {}) }
        : {}),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new ApiError("network_error", "无法连接服务，请检查网络后重试。", 0);
  }
  if (!response.headers.get("content-type")?.includes("application/json"))
    throw new ApiError(
      "invalid_response",
      "服务响应异常，请稍后重试。",
      response.status,
    );
  let payload: Envelope<T>;
  try {
    payload = await response.json();
  } catch {
    throw new ApiError(
      "invalid_response",
      "服务响应异常，请稍后重试。",
      response.status,
    );
  }
  if (
    !payload ||
    typeof payload.ok !== "boolean" ||
    (!payload.ok && !payload.error?.message)
  )
    throw new ApiError(
      "invalid_response",
      "服务响应异常，请稍后重试。",
      response.status,
    );
  if (!payload.ok)
    throw new ApiError(
      payload.error.code,
      payload.error.message,
      response.status,
    );
  if (!response.ok)
    throw new ApiError(
      "request_failed",
      "请求未完成，请稍后重试。",
      response.status,
    );
  return payload.data;
}
