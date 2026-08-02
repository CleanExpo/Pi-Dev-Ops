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
  const upstreamUrl = `${base}/api/swarm/curator/proposals${qs ? `?${qs}` : ""}`;

  try {
    const upstream = await fetch(upstreamUrl, {
      headers: _authHeaders(),
      signal: AbortSignal.timeout(5_000),
      cache: "no-store",
    });
    const body = await upstream.json().catch(() => ({}));

    // This route is UNAUTHENTICATED (deliberately — see __tests__/api-auth-classification.json)
    // and reaches upstream with PI_CEO_PASSWORD that the caller does not hold. It used to
    // return the upstream body wholesale, so whatever upstream started returning tomorrow
    // became a public payload with nobody deciding that. "Revisit if the payload widens" is an
    // intention, not a control.
    //
    // Fail CLOSED on an unexpected key rather than dropping it silently: a silent drop hides a
    // real upstream change just as effectively, and this way the widening is impossible to miss
    // and cheap to accept deliberately by adding the key here.
    // Allowed key PATHS, not just top-level keys. Round-1 review: the first version checked
    // only the top level, so upstream could widen the objects INSIDE `proposals` and every new
    // field reached anonymous callers. `proposals` is an array of objects — the interesting
    // payload was entirely below the level being checked.
    const ALLOWED_PATHS = new Set([
      "count", "status", "limit", "total", "error", "detail",
      "proposals",
      "proposals[].id", "proposals[].skill", "proposals[].status",
      "proposals[].created_at", "proposals[].summary", "proposals[].rationale",
    ]);

    /** Every key path in the payload, arrays collapsed to `[]` so shape not length matters. */
    const keyPaths = (v: unknown, prefix = ""): string[] => {
      if (Array.isArray(v)) return v.flatMap((x) => keyPaths(x, `${prefix}[]`));
      if (v && typeof v === "object") {
        return Object.entries(v as Record<string, unknown>).flatMap(([k, val]) => {
          const path = prefix ? `${prefix}.${k}` : k;
          return [path, ...keyPaths(val, path)];
        });
      }
      return [];
    };

    const payload = upstream.ok ? body : { error: `HTTP ${upstream.status}`, ...body };
    const unexpected = [...new Set(keyPaths(payload))].filter((k) => !ALLOWED_PATHS.has(k));
    if (unexpected.length > 0) {
      console.error("[curator-proposals] upstream returned unexpected key paths:", unexpected);
      return _quietError(
        "upstream payload shape changed",
        "response withheld: this surface is public, so an unreviewed key is not published",
      );
    }

    return Response.json(payload, {
      status: 200,
      headers: { "X-Upstream-Status": String(upstream.status) },
    });
  } catch (exc) {
    return _quietError("upstream unreachable", String(exc));
  }
}
