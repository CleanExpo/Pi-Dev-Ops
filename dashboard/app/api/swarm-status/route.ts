// app/api/swarm-status/route.ts — proxy Railway /api/autonomy/status (RA-1092)
// Surfaces swarm state, autonomous PR counts and green-merge progress for /control.

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

async function fetchUpstream(): Promise<SwarmStatus | null> {
  const base = process.env.RAILWAY_URL ?? process.env.PI_CEO_URL;
  if (!base) return null;

  try {
    // Was `Authorization: Bearer ${PI_CEO_PASSWORD}` — a raw password where upstream requires
    // a signed session token. It never authenticated, so fetchUpstream() always returned null
    // and the route served fallback(), i.e. `state: "OFF"`. The dashboard has been reporting
    // the swarm as OFF because it could not ask, not because it looked. See
    // lib/pi-ceo-session.ts.
    const res = await piCeoFetch("/api/autonomy/status", {}, 5_000);
    if (!res || !res.ok) return null;
    const raw = (await res.json()) as Record<string, unknown>;

    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
    // `enabled` is the autonomy poller's configuration, not observed swarm work.
    const state: SwarmStatus["state"] = raw.stale === true ? "UNKNOWN" : raw.rate_limited === true
      ? "RATE_LIMITED"
      : raw.swarm_enabled === false
        ? "OFF"
        : raw.swarm_shadow === true
          ? "SHADOW"
          : raw.swarm_running === true ? "ACTIVE" : "UNKNOWN";
    const count = (value: unknown) => typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;

    return {
      state,
      autonomous_prs_today: count(raw.autonomous_prs_today),
      autonomous_prs_limit: count(raw.autonomous_prs_limit),
      green_merges: count(raw.green_merges),
      green_merges_target: count(raw.green_merges_target),
      last_pr_ts: typeof raw.last_pr_ts === "string" ? raw.last_pr_ts : null,
      last_pr_url: typeof raw.last_pr_url === "string" && raw.last_pr_url.startsWith("https://") ? raw.last_pr_url : null,
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
