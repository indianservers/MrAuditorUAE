import {
  clearTokens,
  failure,
  noStore,
  rotate,
  sameOrigin,
  setTokens,
} from "@/lib/auth/server";
import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) return failure(403, "Same-origin request required");
  const token = (await cookies()).get("auditos_refresh")?.value;
  if (!token) return failure(401, "Please sign in");
  try {
    const tokens = await rotate(token);
    if (!tokens) {
      await clearTokens();
      return failure(401, "Session expired");
    }
    await setTokens(tokens);
    return NextResponse.json({ authenticated: true }, { headers: noStore });
  } catch {
    return failure(503, "Session service unavailable");
  }
}
