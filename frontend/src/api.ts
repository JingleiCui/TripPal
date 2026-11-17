/** 统一请求层：错误契约、请求追踪、超时与登录态失效通知。 */

export const AUTH_EXPIRED_EVENT = "travel-agent:auth-expired";

const STATUS_CODES: Record<number, string> = {
  400: "bad_request",
  401: "unauthorized",
  403: "forbidden",
  404: "not_found",
  409: "conflict",
  413: "payload_too_large",
  422: "validation_error",
  429: "rate_limited",
  500: "internal_error",
  502: "upstream_error",
  503: "service_unavailable",
  504: "upstream_timeout",
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId?: string;

  constructor(message: string, status: number, code: string, requestId?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }

  get isNetwork(): boolean {
    return this.status === 0;
  }

  get isAuth(): boolean {
    return this.status === 401;
  }
}

let csrf = "";

export function setCsrf(value: string) {
  csrf = value;
}

export function getCsrf(): string {
  return csrf;
}

function newRequestId(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return Math.random().toString(36).slice(2) + Date.now().toString(36);
  }
}

type ApiOptions = RequestInit & { timeoutMs?: number };

type ErrorBody = {
  detail?: unknown;
  error?: { code?: string; message?: string; request_id?: string };
};

function readableMessage(
  body: ErrorBody | null,
  status: number,
  requestId: string,
): string {
  if (typeof body?.detail === "string" && body.detail.trim()) return body.detail;
  if (body?.error?.message?.trim()) return body.error.message;
  if (status === 400 || status === 422)
    return "输入内容不符合要求，请检查日期、天数等字段";
  if (status === 401) return "登录状态已失效，请重新登录";
  if (status === 403) return "当前操作没有权限";
  if (status === 404) return "请求的内容不存在或已被删除";
  if (status === 409) return "行程已被其他修改更新，请刷新后再试";
  if (status === 429) return "操作过于频繁，请稍后再试";
  if (status >= 500)
    return `服务暂时不可用，请稍后重试（请求编号 ${requestId.slice(0, 8)}）`;
  return "请求失败，请稍后重试";
}

export async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { timeoutMs = 0, signal, ...rest } = options;
  const headers = new Headers(rest.headers);
  if (rest.body && !(rest.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (csrf) headers.set("X-CSRF-Token", csrf);
  const requestId = newRequestId();
  headers.set("X-Request-Id", requestId);

  const controller = new AbortController();
  const onAbort = () => controller.abort();
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener("abort", onAbort, { once: true });
  }
  let timedOut = false;
  const timer =
    timeoutMs > 0
      ? window.setTimeout(() => {
          timedOut = true;
          controller.abort();
        }, timeoutMs)
      : null;

  let response: Response;
  try {
    response = await fetch("/api/v1" + path, {
      ...rest,
      headers,
      signal: controller.signal,
      credentials: "same-origin",
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      if (timedOut)
        throw new ApiError("请求超时，请检查网络或稍后重试", 0, "timeout", requestId);
      throw error; // 调用方主动取消，保持 AbortError 语义
    }
    throw new ApiError(
      "暂时无法连接服务，请检查网络后重试",
      0,
      "network_error",
      requestId,
    );
  } finally {
    signal?.removeEventListener("abort", onAbort);
    if (timer !== null) window.clearTimeout(timer);
  }

  if (!response.ok) {
    let body: ErrorBody | null = null;
    try {
      body = (await response.json()) as ErrorBody;
    } catch {
      body = null;
    }
    const error = new ApiError(
      readableMessage(body, response.status, requestId),
      response.status,
      body?.error?.code ?? STATUS_CODES[response.status] ?? "request_failed",
      body?.error?.request_id ?? requestId,
    );
    // /auth/me 的 401 是未登录的正常探测，不能触发全局退出，否则会循环。
    if (error.isAuth && path !== "/auth/me") {
      window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT, { detail: error }));
    }
    throw error;
  }

  if (response.status === 204) return undefined as T;
  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(
      "服务返回了无法解析的内容",
      response.status,
      "invalid_response",
      requestId,
    );
  }
}

export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
