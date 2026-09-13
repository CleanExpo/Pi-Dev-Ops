// GET /api/mesh-fleet — UNI-2649 BFF for the Mission Control Fleet tile.
//
// Upstream GET /api/mesh/fleet requires X-Pi-CEO-Secret. That path is
// deliberately absent from the pi-ceo proxy allowlist so the browser never
// holds the secret. This route attaches the secret on the server, projects
// host / revision / heartbeat / claim, and stamps checkedAt.
//
// A failed read is HTTP 503 `{ status: "unavailable" }`, never a 200 empty
// fleet. Auth is the dashboard session: /api/mesh-fleet is in
// PROTECTED_API_PREFIXES.

import { projectFleet, unavailableFleet } from "@/lib/control/mesh-fleet";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const NO_STORE = { "Cache-Control": "no-store" };

function meshSecret(): string {
  return (
    process.env.TAO_INTERNAL_WEBHOOK_SECRET ||
    process.env.TAO_WEBHOOK_SECRET ||
    ""
  ).trim();
}

function ceoBase(): string {
  return (process.env.RAILWAY_URL ?? process.env.PI_CEO_URL ?? "")
    .replace(/\/$/, "")
    .trim();
}

function nowIso(): string {
  return new Date().toISOString();
}

function unavailable(reason: string): Response {
  return Response.json(unavailableFleet(reason, nowIso()), {
    status: 503,
    headers: NO_STORE,
  });
}

async function readUpstream(base: string, secret: string): Promise<unknown | null> {
  const res = await fetch(`${base}/api/mesh/fleet`, {
    headers: { "X-Pi-CEO-Secret": secret },
    signal: AbortSignal.timeout(8_000),
    cache: "no-store",
  }).catch(() => null);
  if (!res || !res.ok) return null;
  return res.json().catch(() => null);
}

export async function GET(): Promise<Response> {
  const secret = meshSecret();
  if (!secret) return unavailable("mesh secret not configured");
  const base = ceoBase();
  if (!base) return unavailable("Pi-CEO URL not configured");

  const raw = await readUpstream(base, secret);
  if (raw === null) return unavailable("upstream unreachable");

  const view = projectFleet(raw, nowIso());
  if (view.status === "unavailable") {
    return Response.json(view, { status: 503, headers: NO_STORE });
  }
  return Response.json(view, { status: 200, headers: NO_STORE });
}
