// app/api/curator-proposals/route.ts — RA-1839: read-only proxy for
// /api/swarm/curator/proposals.
//
// Forwards `status` + `limit` query params straight through.

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function _baseUrl(): string | null {
  const raw = process.env.RAILWAY_URL ?? process.env.PI_CEO_URL;
  return raw ? raw.replace(/\/$/, "") : null;
}

function _authHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (process.env.PI_CEO_PASSWORD) {
    headers.Authorization = `Bearer ${process.env.PI_CEO_PASSWORD}`;
  }
  return headers;
}

export async function GET(request: Request): Promise<Response> {
  const base = _baseUrl();
  if (!base) {
    return Response.json(
      { error: "PI_CEO_URL / RAILWAY_URL not configured" },
      { status: 503 },
    );
  }

  const { searchParams } = new URL(request.url);
  const out = new URLSearchParams();
  const status = searchParams.get("status");
  const limit = searchParams.get("limit");
  if (status) out.set("status", status);
  if (limit) out.set("limit", limit);
  const qs = out.toString();
  const upstreamUrl = `${base}/api/swarm/curator/proposals${qs ? `?${qs}` : ""}`;

  try {
    const upstream = await fetch(upstreamUrl, {
      headers: _authHeaders(),
      signal: AbortSignal.timeout(5_000),
      cache: "no-store",
    });
    const body = await upstream.json().catch(() => ({}));
    return Response.json(body, { status: upstream.status });
  } catch (exc) {
    return Response.json(
      { error: "upstream unreachable", detail: String(exc) },
      { status: 502 },
    );
  }
}
