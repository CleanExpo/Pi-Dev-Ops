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

// The record fields swarm/meta_curator.py writes (propose_from_cluster,
// accept/reject/expire), minus proposed_skill_content, which the backend
// strips from list responses. RA-7848: this list used to name id / skill /
// summary / rationale, which the backend never sends, so every real
// proposal was withheld as "upstream payload shape changed".
const PROPOSAL_FIELDS = [
  "ts", "proposal_id", "cluster_id", "trigger_source", "cluster_summary", "evidence_count",
  "proposed_skill_name", "proposed_skill_path", "status", "created_at", "draft_id", "error",
  "reason", "accepted_at", "skill_path_written", "rejected_at", "expired_at",
];

const ALLOWED_PATHS = new Set([
  "count", "status", "limit", "total", "returned", "by_status", "error", "detail",
  "proposals",
  ...PROPOSAL_FIELDS.map((field) => `proposals[].${field}`),
]);

/** Every payload key path, with array positions collapsed to `[]`. */
function keyPaths(value: unknown, prefix = ""): string[] {
  if (Array.isArray(value)) return value.flatMap((item) => keyPaths(item, `${prefix}[]`));
  if (!value || typeof value !== "object") return [];
  return Object.entries(value as Record<string, unknown>).flatMap(([key, item]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return [path, ...keyPaths(item, path)];
  });
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
    const payload = upstream.ok ? body : { error: `HTTP ${upstream.status}`, ...body };
    // by_status is keyed by status name (pending, accepted, rejected_dedup, ...), and each count
    // is a plain number, so any key under it is expected.
    const unexpected = [...new Set(keyPaths(payload))].filter(
      (key) => !ALLOWED_PATHS.has(key) && !key.startsWith("by_status."),
    );
    if (unexpected.length > 0) {
      console.error("[curator-proposals] upstream returned unexpected key paths:", unexpected);
      return _quietError("upstream payload shape changed", "response withheld pending review");
    }
    return Response.json(payload, {
      status: 200,
      headers: { "X-Upstream-Status": String(upstream.status) },
    });
  } catch (exc) {
    return _quietError("upstream unreachable", String(exc));
  }
}
