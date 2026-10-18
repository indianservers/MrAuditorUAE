import { NextRequest, NextResponse } from "next/server";
import { backend, failure, noStore, sameOrigin } from "@/lib/auth/server";
export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) return failure(403, "Same-origin request required");
  try {
    let body = "";
    if (request.body) {
      const reader = request.body.getReader();
      const decoder = new TextDecoder();
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        body += decoder.decode(value, { stream: true });
        if (body.length > 4096) {
          await reader.cancel();
          return failure(413, "Invitation request too large");
        }
      }
    }
    const input = JSON.parse(body);
    if (typeof input.token !== "string" || typeof input.password !== "string")
      return failure(422, "Invalid invitation fields");
    const r = await backend("admin/invitations/redeem", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: input.token, password: input.password }),
    });
    return NextResponse.json(await r.json(), {
      status: r.status,
      headers: noStore,
    });
  } catch {
    return failure(422, "Unable to activate this invitation");
  }
}
