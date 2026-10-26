import { backend, failure, noStore, sameOrigin } from "@/lib/auth/server";
import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
const allowed =
  /^(tenants|workspace(?:\/.*)?|clients(?:\/[a-f0-9-]+)?|entities(?:\/[a-f0-9-]+)?|engagements(?:\/[a-f0-9-]+(?:\/audit(?:\/[a-z0-9-]+)*)?)?|admin(?:\/[a-z0-9-]+)*|client-portal(?:\/[a-z0-9-]+)*|financial-periods|accounting(?:\/.*)?|analytics(?:\/.*)?|reconciliation(?:\/.*)?|sampling(?:\/.*)?|connectors(?:\/.*)?|vat(?:\/.*)?|tax(?:\/.*)?|ifrs(?:\/.*)?|ai(?:\/.*)?|jobs(?:\/.*)?)$/;
async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const path = (await context.params).path.join("/");
  if (
    (!allowed.test(path) &&
      !/^(?:jurisdictions|intelligence|regulatory|collaboration)\/[a-zA-Z0-9/-]+$/.test(
        path,
      ) &&
      !/^(?:tp|ml|dmtt|grc|governance|platform|subscriptions)(?:\/[a-zA-Z0-9/-]+)?$/.test(
        path,
      ) &&
      !/^auth\/mfa(?:\/(?:enroll|confirm))?$/.test(path)) ||
    path.includes("..") ||
    path.includes("%")
  )
    return failure(404, "Unknown API resource");
  if (request.method !== "GET" && !sameOrigin(request))
    return failure(403, "Same-origin request required");
  const token = (await cookies()).get("auditos_access")?.value;
  if (!token) return failure(401, "Please sign in");
  const headers = new Headers({ Authorization: `Bearer ${token}` });
  for (const key of ["content-type", "x-tenant-id", "idempotency-key"]) {
    const v = request.headers.get(key);
    if (v) headers.set(key, v);
  }
  const max = 64 * 1024 * 1024 + 65536;
  if (Number(request.headers.get("content-length") || 0) > max)
    return failure(413, "Upload exceeds 64 MiB");
  try {
    // Count bytes before buffering: content-length is not trusted.
    let size = 0;
    const chunks: Uint8Array[] = [];
    if (request.method !== "GET" && request.body) {
      const reader = request.body.getReader();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > max) {
          await reader.cancel();
          return failure(413, "Upload exceeds 64 MiB");
        }
        chunks.push(value);
      }
    }
    const body = chunks.length ? Buffer.concat(chunks) : undefined;
    const r = await backend(path + request.nextUrl.search, {
      method: request.method,
      headers,
      body,
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(120_000)]),
    });
    return new NextResponse(r.body, {
      status: r.status,
      headers: {
        ...noStore,
        "Content-Type": r.headers.get("content-type") || "application/json",
        ...(r.headers.get("content-disposition")
          ? { "Content-Disposition": r.headers.get("content-disposition")! }
          : {}),
        ...(r.headers.get("x-export-sha256")
          ? { "X-Export-SHA256": r.headers.get("x-export-sha256")! }
          : {}),
        ...(r.headers.get("content-security-policy")
          ? {
              "Content-Security-Policy": r.headers.get(
                "content-security-policy",
              )!,
            }
          : {}),
      },
    });
  } catch {
    return failure(
      503,
      "Backend unavailable. Your request may have completed; refresh before retrying a mutation.",
    );
  }
}
export { proxy as GET, proxy as PATCH, proxy as POST, proxy as PUT };
