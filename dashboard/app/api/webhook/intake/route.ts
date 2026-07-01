// app/api/webhook/intake/route.ts — UNI-2214 item 1 closed-loop push-intake surface.
// Validates X-Intake-Secret against INTAKE_WEBHOOK_SECRET before proxying to the
// FastAPI backend (/api/webhook/intake). Without this Vercel handler a bare
// /api/webhook/intake never reaches Railway and returns a spurious 200 — the
// same proxy pattern the morning-intel webhook uses (RA-1686).
export const dynamic = "force-dynamic";

import { NextRequest, NextResponse } from "next/server";
import { timingSafeEqual } from "crypto";

const PI_CEO_URL = (process.env.PI_CEO_URL ?? "http://127.0.0.1:7777").replace(/\/$/, "");
const INTAKE_WEBHOOK_SECRET = process.env.INTAKE_WEBHOOK_SECRET ?? "";

export async function POST(req: NextRequest): Promise<NextResponse> {
  const incoming = req.headers.get("x-intake-secret") ?? "";

  // Config-independent 401: a request with no secret header is always rejected,
  // and an unset server secret means we cannot verify so we reject all. Keeps
  // the unauthenticated smoke probe stable at 401 whether or not the secret is
  // configured, and never accepts anonymous intake.
  if (!INTAKE_WEBHOOK_SECRET || !incoming) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  // Timing-safe comparison (pad to equal length).
  const maxLen = Math.max(incoming.length, INTAKE_WEBHOOK_SECRET.length);
  const a = Buffer.from(incoming.padEnd(maxLen));
  const b = Buffer.from(INTAKE_WEBHOOK_SECRET.padEnd(maxLen));
  if (!timingSafeEqual(a, b)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await req.text();
  const res = await fetch(`${PI_CEO_URL}/api/webhook/intake`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Intake-Secret": incoming,
    },
    body,
    signal: AbortSignal.timeout(10_000),
  }).catch(() => null);

  if (!res) return NextResponse.json({ error: "Backend unreachable" }, { status: 502 });
  const data = await res.text();
  return new NextResponse(data, { status: res.status, headers: { "Content-Type": "application/json" } });
}
