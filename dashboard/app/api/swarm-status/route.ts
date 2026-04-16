// app/api/swarm-status/route.ts — proxy Railway /api/autonomy/status (RA-1092)
// Surfaces swarm state, autonomous PR counts and green-merge progress for /control.

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

interface SwarmStatus {
  state: "SHADOW" | "ACTIVE" | "RATE_LIMITED" | "OFF";
  autonomous_prs_today: number;
  autonomous_prs_limit: number;
  green_merges: number;
  green_merges_target: number;
  last_pr_ts: string | null;
  last_pr_url: string | null;
}

function fallback(): SwarmStatus {
  return {
    state: "OFF",
    autonomous_prs_today: 0,
    autonomous_prs_limit: 3,
    green_merges: 0,
    green_merges_target: 20,
    last_pr_ts: null,
    last_pr_url: null,
  };
}

async function fetchUpstream(): Promise<SwarmStatus | null> {
  const base = process.env.RAILWAY_URL ?? process.env.PI_CEO_URL;
  if (!base) return null;

  const url = `${base.replace(/\/$/, "")}/api/autonomy/status`;
  try {
    const res = await fetch(url, {
      signal: AbortSignal.timeout(5_000),
      headers: process.env.PI_CEO_PASSWORD
        ? { Authorization: `Bearer ${process.env.PI_CEO_PASSWORD}` }
        : {},
    });
    if (!res.ok) return null;
    const raw = (await res.json()) as Record<string, unknown>;

    // Normalise — accept a few field-name variants the backend might return.
    const shadow = Boolean(raw.swarm_shadow ?? raw.shadow);
    const enabled = Boolean(raw.swarm_enabled ?? raw.enabled);
    const rateLimited = Boolean(raw.rate_limited);
    const state: SwarmStatus["state"] = rateLimited
      ? "RATE_LIMITED"
      : !enabled
        ? "OFF"
        : shadow
          ? "SHADOW"
          : "ACTIVE";

    return {
      state,
      autonomous_prs_today: Number(raw.autonomous_prs_today ?? raw.prs_today ?? 0),
      autonomous_prs_limit: Number(raw.autonomous_prs_limit ?? raw.prs_limit ?? 3),
      green_merges: Number(raw.green_merges ?? raw.merges_green ?? 0),
      green_merges_target: Number(raw.green_merges_target ?? raw.merges_target ?? 20),
      last_pr_ts: (raw.last_pr_ts as string | null) ?? null,
      last_pr_url: (raw.last_pr_url as string | null) ?? null,
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
