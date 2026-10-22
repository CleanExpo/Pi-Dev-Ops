// app/api/phone/progress/route.ts — Phone companion progress surface (RA-1686)
// Verifies the pi_session cookie before proxying to Railway; returns 401 otherwise.
export const dynamic = "force-dynamic";

import { NextRequest, NextResponse } from "next/server";
import { requestHasValidSession } from "@/lib/auth-secret";

const PI_CEO_URL = (process.env.PI_CEO_URL ?? "http://127.0.0.1:7777").replace(/\/$/, "");

export async function POST(req: NextRequest): Promise<NextResponse> {
  if (!(await requestHasValidSession(req))) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const cookie = req.headers.get("cookie") ?? "";

  const body = await req.text();
  const res = await fetch(`${PI_CEO_URL}/api/phone/progress`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Cookie: cookie },
    body,
    signal: AbortSignal.timeout(10_000),
  }).catch(() => null);

  if (!res) return NextResponse.json({ error: "Backend unreachable" }, { status: 502 });
  const data = await res.text();
  return new NextResponse(data, { status: res.status, headers: { "Content-Type": "application/json" } });
}
