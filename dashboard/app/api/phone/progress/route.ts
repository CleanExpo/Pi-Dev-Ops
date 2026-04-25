// app/api/phone/progress/route.ts — Phone companion progress surface (RA-1686)
// Checks session cookie before proxying to Railway; returns 401 if missing.
export const dynamic = "force-dynamic";

import { NextRequest, NextResponse } from "next/server";

const PI_CEO_URL = (process.env.PI_CEO_URL ?? "http://127.0.0.1:7777").replace(/\/$/, "");

export async function POST(req: NextRequest): Promise<NextResponse> {
  const cookie = req.headers.get("cookie") ?? "";
  if (!cookie.includes("tao_session=")) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

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
