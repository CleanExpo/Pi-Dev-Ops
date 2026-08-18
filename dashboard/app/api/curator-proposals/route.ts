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

// The upstream contract, taken from the two places that define it rather than guessed:
// the record built at swarm/meta_curator.py:518-529, and the response assembled at
// app/server/routes/swarm.py:251-258 (which strips `proposed_skill_content` from the list
// view because it is the whole SKILL.md body).
//
// The previous list named `proposals[].id`, `.skill`, `.summary` and `.rationale`. Upstream
// has never sent those. It emits `proposal_id`, `proposed_skill_name`, `cluster_summary`
// and `ts`, and has done since 2026-07-01 — a month before this list was written on
// 2026-08-03 (#609). So every response failed the check, the route returned "upstream
// payload shape changed" and withheld the body, and the panel has been dark since it
// shipped. Not drift: the list never matched either side.
//
// `CuratorProposalsPanel.tsx` reads exactly these names (`p.proposal_id`, `p.ts`,
// `p.cluster_id`, `p.proposed_skill_name`, `p.cluster_summary`, `p.evidence_count`), so the
// component and the backend already agreed with each other. Only this list disagreed.
const ALLOWED_PATHS = new Set([
  "total", "returned", "by_status", "proposals", "error", "detail",
  // Accepted on the error path built below, and by older upstreams.
  "count", "status", "limit",
  "proposals[].ts", "proposals[].proposal_id", "proposals[].cluster_id",
  "proposals[].trigger_source", "proposals[].cluster_summary",
  "proposals[].evidence_count", "proposals[].proposed_skill_name",
  "proposals[].proposed_skill_path", "proposals[].status",
  "proposals[].created_at", "proposals[].draft_id", "proposals[].reason",
]);

/** `by_status` is a Record<string, number> keyed by status, so its keys cannot be enumerated.
 *
 * Allow-listing the bare `by_status` was why `by_status.pending` tripped the guard — and any
 * other status would have too. The set of statuses is open (pending, accepted,
 * rejected_dedup, rejected_cooloff, rejected_rate, expired, queued_dry_run, and `unknown`
 * when a record has none), so a fixed list here would go stale the next time one is added.
 * Depth is still bounded: only direct children of `by_status` pass.
 */
function isAllowedPath(path: string): boolean {
  if (ALLOWED_PATHS.has(path)) return true;
  return /^by_status\.[^.]+$/.test(path);
}

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
    const unexpected = [...new Set(keyPaths(payload))].filter((key) => !isAllowedPath(key));
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
