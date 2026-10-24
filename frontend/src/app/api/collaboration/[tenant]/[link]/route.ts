import { backend, failure, noStore, sameOrigin } from "@/lib/auth/server";
import { NextRequest, NextResponse } from "next/server";

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ tenant: string; link: string }> },
) {
  const { tenant, link } = await context.params;
  if (!/^[a-f0-9-]{36}$/.test(tenant) || !/^[a-f0-9-]{36}$/.test(link))
    return failure(404, "Client link unavailable");
  if (request.method !== "GET" && !sameOrigin(request))
    return failure(403, "Same-origin request required");
  const token = request.headers.get("x-collaboration-token") || "";
  if (!/^[a-f0-9]{64}$/.test(token))
    return failure(404, "Client link unavailable");
  const headers = new Headers({ "X-Collaboration-Token": token });
  const type = request.headers.get("content-type");
  if (type) headers.set("Content-Type", type);
  const maximum = 26 * 1024 * 1024;
  if (Number(request.headers.get("content-length") || 0) > maximum)
    return failure(413, "Upload limit exceeded");
  const chunks: Uint8Array[] = [];
  let bytes = 0;
  if (request.method !== "GET" && request.body) {
    const reader = request.body.getReader();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > maximum) {
        await reader.cancel();
        return failure(413, "Upload limit exceeded");
      }
      chunks.push(value);
    }
  }
  try {
    const response = await backend(`collaboration/public/${tenant}/${link}`, {
      method: request.method,
      headers,
      body: chunks.length ? Buffer.concat(chunks) : undefined,
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(120000)]),
    });
    return new NextResponse(response.body, {
      status: response.status,
      headers: {
        ...noStore,
        "Content-Type": "application/json",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch {
    return failure(503, "Client collaboration temporarily unavailable");
  }
}
export { proxy as GET, proxy as POST };
