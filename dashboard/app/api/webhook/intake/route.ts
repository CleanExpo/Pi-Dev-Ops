// app/api/webhook/intake/route.ts — UNI-2214 item 1 closed-loop push-intake surface.
// Validates X-Intake-Secret against INTAKE_WEBHOOK_SECRET before proxying to the
// FastAPI backend (/api/webhook/intake). Without this Vercel handler a bare
// /api/webhook/intake never reaches Railway and returns a spurious 200 — the
// same proxy pattern the morning-intel webhook uses (RA-1686).
export const dynamic = "force-dynamic";

import { NextRequest, NextResponse } from "next/server";
import { createHash, timingSafeEqual } from "crypto";

const PI_CEO_URL = (process.env.PI_CEO_URL ?? "http://127.0.0.1:7777").replace(/\/$/, "");
// .trim() — Vercel appends a trailing newline to env values; an untrimmed
// secret ("s3cr3t\n") would never match the header and reject all traffic.
const INTAKE_WEBHOOK_SECRET = (process.env.INTAKE_WEBHOOK_SECRET ?? "").trim();

// Constant-time compare via SHA-256 digests: fixed 32-byte length regardless of
// input, so timingSafeEqual never throws on a length mismatch (Buffer UTF-8 vs
// String.padEnd UTF-16 code-unit skew) and the comparison stays timing-safe.
function secretsMatch(a: string, b: string): boolean {
  return timingSafeEqual(
    createHash("sha256").update(a).digest(),
    createHash("sha256").update(b).digest(),
  );
}

export async function POST(req: NextRequest): Promise<NextResponse> {
  const incoming = req.headers.get("x-intake-secret") ?? "";

  // Config-independent 401: a request with no secret header is always rejected,
  // and an unset server secret means we cannot verify so we reject all. Keeps
  // the unauthenticated smoke probe stable at 401 whether or not the secret is
  // configured, and never accepts anonymous intake.
  if (!INTAKE_WEBHOOK_SECRET || !incoming) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  if (!secretsMatch(incoming, INTAKE_WEBHOOK_SECRET)) {
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
