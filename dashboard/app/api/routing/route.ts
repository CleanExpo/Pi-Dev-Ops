// app/api/routing/route.ts — RA-7434 dashboard surface for Mission Control.
//
// Smoke and the founder-facing UI hit GET /api/routing on Vercel. The payload
// lives on Railway (app/server/routes/routing.py). Until this file existed the
// production probe 404'd: FastAPI registered the route, the dashboard did not.
//
// Auth: proxy.ts requires a pi_session cookie. This handler then borrows a
// Railway session via piCeoFetch — the same path as model-fabric / swarm-status.
// Do not attach TAO_WEBHOOK_SECRET here; upstream accepts the session cookie.

import { piCeoFetch } from "@/lib/pi-ceo-session";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(): Promise<Response> {
  try {
    const res = await piCeoFetch("/api/routing", {}, 8_000);
    if (!res) {
      return Response.json(
        { error: "Pi-CEO unavailable" },
        { status: 503, headers: { "Cache-Control": "no-store" } },
      );
    }
    const body = await res.text();
    return new Response(body, {
      status: res.status,
      headers: {
        "Content-Type": res.headers.get("content-type") ?? "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    return Response.json(
      {
        error: error instanceof Error ? error.message : "Routing status failed",
      },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
