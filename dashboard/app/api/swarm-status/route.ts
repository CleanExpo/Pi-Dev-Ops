// app/api/swarm-status/route.ts — proxy Railway /api/swarm/status (RA-1092, re-pointed RA-7849)
// Surfaces swarm state and the daily autonomous-PR quota for /control.

import { piCeoFetch } from "@/lib/pi-ceo-session";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

interface SwarmStatus {
  state: "SHADOW" | "ACTIVE" | "RATE_LIMITED" | "OFF" | "UNKNOWN";
  autonomous_prs_today: number | null;
  autonomous_prs_limit: number | null;
  green_merges: number | null;
  green_merges_target: number | null;
  last_pr_ts: string | null;
  last_pr_url: string | null;
}

function fallback(): SwarmStatus {
  return {
    state: "UNKNOWN",
    autonomous_prs_today: null,
    autonomous_prs_limit: null,
    green_merges: null,
    green_merges_target: null,
    last_pr_ts: null,
    last_pr_url: null,
  };
}

// RA-7849: this used to read swarm_enabled / swarm_running / autonomous_prs_* from
// /api/autonomy/status, which returns none of them (it describes the Linear
// poller), so the page always said UNKNOWN. /api/swarm/status is the swarm's own
// state: the TAO_SWARM_ENABLED gate app_factory uses to start the orchestrator,
// the shadow flag, the kill switch and the daily PR quota. It has no merge or
// last-PR data, so those stay null rather than invented.
function stateFrom(raw: Record<string, unknown>, used: number | null, limit: number | null): SwarmStatus["state"] {
  if (raw.swarm_enabled_env !== true || raw.kill_switch_active === true) return "OFF";
  if (used !== null && limit !== null && limit > 0 && used >= limit) return "RATE_LIMITED";
  if (raw.swarm_shadow_env === true) return "SHADOW";
  if (raw.swarm_shadow_env === false) return "ACTIVE";
  return "UNKNOWN";
}

async function fetchUpstream(): Promise<SwarmStatus | null> {
  const base = process.env.RAILWAY_URL ?? process.env.PI_CEO_URL;
  if (!base) return null;

  try {
    const res = await piCeoFetch("/api/swarm/status", {}, 5_000);
    if (!res || !res.ok) return null;
    const raw = (await res.json()) as Record<string, unknown>;
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
    if (typeof raw.swarm_enabled_env !== "boolean") return null;

    const count = (value: unknown) => typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
    const quota = raw.pr_quota && typeof raw.pr_quota === "object" ? raw.pr_quota as Record<string, unknown> : {};
    const used = count(quota.used);
    const limit = count(quota.limit);
    return {
      state: stateFrom(raw, used, limit),
      autonomous_prs_today: used,
      autonomous_prs_limit: limit,
      green_merges: null,
      green_merges_target: null,
      last_pr_ts: null,
      last_pr_url: null,
    };
  } catch {
    return null;
  }
}

export async function GET(): Promise<Response> {
  const data = (await fetchUpstream()) ?? fallback();
  return Response.json(data, {
    headers: { "Cache-Control": "no-store" },
  });
}
