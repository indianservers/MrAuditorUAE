import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import "server-only";

export const origin = () => {
  const url = new URL(
    process.env.AUDITOS_API_ORIGIN || "http://127.0.0.1:8000",
  );
  if (
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.pathname !== "/"
  )
    throw new Error("Invalid API origin");
  return url.origin;
};
export const noStore = { "Cache-Control": "no-store" };
export function sameOrigin(request: NextRequest) {
  // Next's internal request origin can differ behind a reverse proxy. Never trust
  // forwarded headers for CSRF validation; compare with the configured public origin.
  const publicOrigin =
    process.env.AUDITOS_WEB_ORIGIN || "http://127.0.0.1:3000";
  return (
    request.headers.get("origin") === publicOrigin &&
    request.headers.get("sec-fetch-site") !== "cross-site"
  );
}
type Tokens = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
};
export async function setTokens(tokens: Tokens) {
  const jar = await cookies();
  const options = {
    httpOnly: true,
    secure:
      process.env.NODE_ENV === "production" ||
      process.env.AUDITOS_COOKIE_SECURE === "true",
    sameSite: "strict" as const,
    path: "/",
  };
  jar.set("auditos_access", tokens.access_token, {
    ...options,
    maxAge: tokens.expires_in,
  });
  jar.set("auditos_refresh", tokens.refresh_token, {
    ...options,
    maxAge: 7 * 24 * 3600,
  });
}
export async function clearTokens() {
  const jar = await cookies();
  jar.delete("auditos_access");
  jar.delete("auditos_refresh");
}
export async function backend(path: string, init: RequestInit = {}) {
  return fetch(`${origin()}/api/v1/${path}`, {
    ...init,
    cache: "no-store",
    redirect: "error",
    signal: init.signal || AbortSignal.timeout(120_000),
  });
}
export function failure(status: number, message: string) {
  return NextResponse.json(
    { error: { message } },
    { status, headers: noStore },
  );
}

// One rotation per refresh token per process. Short-lived results prevent parallel requests
// in multiple tabs from replaying a freshly consumed refresh token.
const rotations = new Map<
  string,
  { expires: number; promise: Promise<Tokens | null> }
>();
export async function rotate(token: string): Promise<Tokens | null> {
  const key = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(token),
  );
  const id = Buffer.from(key).toString("hex");
  const now = Date.now();
  for (const [k, v] of rotations) if (v.expires < now) rotations.delete(k);
  const previous = rotations.get(id);
  if (previous) return previous.promise;
  const promise = backend("auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: token }),
  }).then(async (r) => (r.ok ? ((await r.json()) as Tokens) : null));
  rotations.set(id, { expires: now + 30_000, promise });
  return promise;
}
