// app/api/webhook/morning-intel/route.ts — Morning-intel ingest surface (RA-1686)
// Validates X-Pi-CEO-Secret against WEBHOOK_SECRET before proxying to Railway.
export const dynamic = "force-dynamic";

import { NextRequest, NextResponse } from "next/server";
import { timingSafeEqual } from "crypto";

const PI_CEO_URL = (process.env.PI_CEO_URL ?? "http://127.0.0.1:7777").replace(/\/$/, "");
const WEBHOOK_SECRET = process.env.WEBHOOK_SECRET ?? "";

export async function POST(req: NextRequest): Promise<NextResponse> {
  const incoming = req.headers.get("x-pi-ceo-secret") ?? "";

  // Always require the secret — if env is unset we can't verify, so reject all.
  if (!WEBHOOK_SECRET || !incoming) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  // Timing-safe comparison (pad to equal length).
  const maxLen = Math.max(incoming.length, WEBHOOK_SECRET.length);
  const a = Buffer.from(incoming.padEnd(maxLen));
  const b = Buffer.from(WEBHOOK_SECRET.padEnd(maxLen));
  if (!timingSafeEqual(a, b)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await req.text();
  const res = await fetch(`${PI_CEO_URL}/api/webhook/morning-intel`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Pi-CEO-Secret": incoming,
    },
    body,
    signal: AbortSignal.timeout(10_000),
  }).catch(() => null);

  if (!res) return NextResponse.json({ error: "Backend unreachable" }, { status: 502 });
  const data = await res.text();
  return new NextResponse(data, { status: res.status, headers: { "Content-Type": "application/json" } });
}
