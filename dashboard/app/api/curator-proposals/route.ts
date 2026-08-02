// app/api/curator-proposals/route.ts — RA-1839: read-only proxy for
// /api/swarm/curator/proposals.
//
// Forwards `status` + `limit` query params straight through.

import { piCeoFetch, isLockedOut } from "@/lib/pi-ceo-session";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function _baseUrl(): string | null {
  const raw = process.env.RAILWAY_URL ?? process.env.PI_CEO_URL;
  return raw ? raw.replace(/\/$/, "") : null;
}


function _quietError(error: string, detail?: string): Response {
  return Response.json(
    {
      error,
      detail,
      total: 0,
      returned: 0,
      by_status: {},
      proposals: [],
    },
    { status: 200 },
  );
}

export async function GET(request: Request): Promise<Response> {
  const base = _baseUrl();
  if (!base) {
    return _quietError("PI_CEO_URL / RAILWAY_URL not configured");
  }

  const { searchParams } = new URL(request.url);
  const out = new URLSearchParams();
  const status = searchParams.get("status");
  const limit = searchParams.get("limit");
  if (status) out.set("status", status);
  if (limit) out.set("limit", limit);
  const qs = out.toString();
  const upstreamPath = `/api/swarm/curator/proposals${qs ? `?${qs}` : ""}`;

  try {
    // _authHeaders() attached `Bearer ${PI_CEO_PASSWORD}` — a password where upstream requires
    // a signed session token, so this never authenticated. See lib/pi-ceo-session.ts.
    const upstream = await piCeoFetch(upstreamPath, {}, 5_000);
    if (!upstream) {
      return _quietError(
        isLockedOut() ? "upstream login locked out (429)" : "could not authenticate upstream",
      );
    }
    const body = await upstream.json().catch(() => ({}));
    return Response.json(
      upstream.ok ? body : { error: `HTTP ${upstream.status}`, ...body },
      { status: 200, headers: { "X-Upstream-Status": String(upstream.status) } },
    );
  } catch (exc) {
    return _quietError("upstream unreachable", String(exc));
  }
}
