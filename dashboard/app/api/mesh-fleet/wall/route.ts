// GET /api/mesh-fleet/wall — Live Wall snapshot (docs/briefs/live-wall-v1.md).
//
// Session-gated: /api/mesh-fleet is in PROTECTED_API_PREFIXES, so every path under it
// needs a dashboard session. The mesh secret stays on the server.
//
// Cached for CACHE_MS so six kiosk screens polling cost the same upstream as one. A
// cached payload keeps the `generated_at` it was built with; the browser compares that
// stamp to its own clock and greys the wall when it ages, so a stuck cache can never
// pass for live data behind an HTTP 200.

import { getWallSnapshot } from "@/lib/wall/source";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(): Promise<Response> {
  return Response.json(await getWallSnapshot(), { status: 200, headers: { "Cache-Control": "no-store" } });
}
