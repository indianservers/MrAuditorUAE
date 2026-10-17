export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public requestId?: string,
  ) {
    super(message);
  }
}
let refreshing: Promise<Response> | undefined;
export async function api<T>(
  path: string,
  init: RequestInit = {},
  tenant?: string,
): Promise<T> {
  const headers = new Headers(init.headers);
  if (tenant) headers.set("X-Tenant-ID", tenant);
  if (
    init.body &&
    !(init.body instanceof FormData) &&
    !headers.has("Content-Type")
  )
    headers.set("Content-Type", "application/json");
  const url = path.startsWith("/api/") ? path : `/api/backend/${path}`;
  let response = await fetch(url, {
    ...init,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });
  if (response.status === 401 && !url.includes("/session")) {
    refreshing ||= fetch("/api/session/refresh", { method: "POST" }).finally(
      () => {
        refreshing = undefined;
      },
    );
    const refreshed = await refreshing;
    if (refreshed.ok)
      response = await fetch(url, {
        ...init,
        headers,
        credentials: "same-origin",
        cache: "no-store",
      });
    else if (refreshed.status === 401 && typeof window !== "undefined")
      window.location.assign("/login");
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new ApiError(
      response.status,
      data.error?.message ||
        data.detail ||
        `Request failed (${response.status})`,
      data.error?.request_id,
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
export function qs(values: Record<string, unknown>) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(values))
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  return p.toString();
}
