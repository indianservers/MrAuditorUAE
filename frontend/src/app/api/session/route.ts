import {
  backend,
  clearTokens,
  failure,
  noStore,
  sameOrigin,
  setTokens,
} from "@/lib/auth/server";
import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
export async function GET() {
  const token = (await cookies()).get("auditos_access")?.value;
  if (!token) return failure(401, "Session expired");
  try {
    const r = await backend("auth/me", {
      headers: { Authorization: `Bearer ${token}` },
    });
    return NextResponse.json(await r.json(), {
      status: r.status,
      headers: noStore,
    });
  } catch {
    return failure(503, "Backend unavailable");
  }
}
export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) return failure(403, "Same-origin request required");
  try {
    if (Number(request.headers.get("content-length") || 0) > 4096)
      return failure(413, "Login body too large");
    let length = 0;
    const chunks: Uint8Array[] = [];
    if (request.body) {
      const reader = request.body.getReader();
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        length += value.byteLength;
        if (length > 4096) {
          await reader.cancel();
          return failure(413, "Login body too large");
        }
        chunks.push(value);
      }
    }
    const { email, password } = JSON.parse(
      Buffer.concat(chunks).toString("utf8"),
    );
    if (
      typeof email !== "string" ||
      typeof password !== "string" ||
      email.length > 254 ||
      password.length > 128
    )
      return failure(422, "Invalid credentials format");
    const r = await backend("auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username: email, password }),
    });
    if (!r.ok)
      return NextResponse.json(await r.json(), {
        status: r.status,
        headers: noStore,
      });
    await setTokens(await r.json());
    return NextResponse.json({ authenticated: true }, { headers: noStore });
  } catch {
    return failure(503, "Authentication service unavailable");
  }
}
export async function DELETE(request: NextRequest) {
  if (!sameOrigin(request)) return failure(403, "Same-origin request required");
  const token = (await cookies()).get("auditos_refresh")?.value;
  try {
    if (token) {
      const r = await backend("auth/logout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: token }),
      });
      if (!r.ok)
        return failure(
          r.status,
          "Logout could not revoke the session. Please retry.",
        );
    }
    await clearTokens();
    return new NextResponse(null, { status: 204, headers: noStore });
  } catch {
    return failure(503, "Logout service unavailable. Please retry.");
  }
}
