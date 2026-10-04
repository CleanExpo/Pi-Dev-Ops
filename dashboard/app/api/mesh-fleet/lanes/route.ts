// GET /api/mesh-fleet/lanes — BFF for the "Claude lanes" board module.
//
// Upstream GET /api/mesh/lane-events requires X-Pi-CEO-Secret (the fleet read
// secret is accepted), so the browser never holds it: this route attaches the
// secret on the server and folds the newest events into one row per session
// (lib/control/mesh-lanes.ts).
//
// A failed read is HTTP 503 `{ status: "unavailable" }`, never a 200 empty
// lane list. Auth is the dashboard session: /api/mesh-fleet is in
// PROTECTED_API_PREFIXES, so this path is gated with it.

import { projectLanes, unavailableLanes } from "@/lib/control/mesh-lanes";
import { ceoBase, meshSecret } from "@/lib/control/mesh-upstream";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const NO_STORE = { "Cache-Control": "no-store" };
/** Newest events folded per read; the backend caps a read at 500. */
const WINDOW = 500;

function unavailable(reason: string): Response {
  return Response.json(unavailableLanes(reason, new Date().toISOString()), { status: 503, headers: NO_STORE });
}

export async function GET(): Promise<Response> {
  const secret = meshSecret();
  if (!secret) return unavailable("mesh secret not configured");
  const base = ceoBase();
  if (!base) return unavailable("Pi-CEO URL not configured");

  const res = await fetch(`${base}/api/mesh/lane-events?newest=true&limit=${WINDOW}`, {
    headers: { "X-Pi-CEO-Secret": secret },
    signal: AbortSignal.timeout(8_000),
    cache: "no-store",
  }).catch(() => null);
  if (!res || !res.ok) return unavailable("upstream unreachable");
  const raw = await res.json().catch(() => null);

  const view = projectLanes(raw, new Date().toISOString());
  return Response.json(view, { status: view.status === "ok" ? 200 : 503, headers: NO_STORE });
}
