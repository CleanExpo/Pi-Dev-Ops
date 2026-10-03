// RA-7898 — routed TEST responses for the boards e2e specs. Synthetic: every
// value here is a fixture for a browser test, never shipped in the page.
import type { Page, Route } from "@playwright/test";

const iso = (agoS = 0) => new Date(Date.now() - agoS * 1000).toISOString();

export function healthyResponses(): Record<string, () => unknown> {
  return {
    "/api/mesh-fleet": () => ({ status: "ok", checkedAt: iso(), machines: [
      { host: "Phill_Desktop", revision: "e3dff5e", lastHeartbeat: iso(8), currentClaim: "RA-7898", stale: false },
      { host: "Phills-Mac-mini", revision: "e3dff5e", lastHeartbeat: iso(21), currentClaim: null, stale: false },
      { host: "Phills-MacBook-Pro", revision: "d124c6a", lastHeartbeat: iso(900), currentClaim: null, stale: true },
    ] }),
    "/api/mesh-fleet/wall": () => ({ generated_at: iso(1), banner: { red: 0, grey: 7 },
      fleet: { status: "ok", reason: "", others: [], machines: [
        { host: "Phill_Desktop", chip: "GREEN", reason: "heartbeat 8s ago", ageSeconds: 8, load1: 1.8, selfReported: true, agents: [] },
      ] },
      stations: ["Capture", "Shape", "Contract", "Build", "Prove", "Ship", "Learn"].map((name) => ({
        id: name.toLowerCase(), name, chip: "GREY", reason: "NO LIVE SOURCE YET" })) }),
    "/api/model-fabric": () => ({ enabled: true, healthy: true, totals: { calls: 1840, failures: 12, fallbacks: 31, strengthened: 4 },
      lanes: { generator: { model: "sonnet", banned: false }, reviewer: { model: "minimax-m3", banned: false }, paid: { model: "api", banned: true } } }),
    "/api/swarm-status": () => ({ state: "SHADOW", autonomous_prs_today: 1, autonomous_prs_limit: 3, green_merges: 4,
      green_merges_target: 20, last_pr_ts: null, last_pr_url: null }),
    "/api/kill-switch": () => ({ swarm_enabled_env: true, kill_switch_active: false, escalation_lock_active: false,
      panic_count_last_hour: 0, approver_allowlist: ["phill", "hermes"], approver_totp_configured: ["phill"] }),
    "/api/curator-proposals": () => ({ total: 1, returned: 1, by_status: { pending: 1 }, proposals: [
      { proposal_id: "p1", ts: iso(3600), status: "pending", proposed_skill_name: "release-notes", cluster_summary: "Release notes drafted by hand 4 times", evidence_count: 4 }] }),
    "/api/command-centre/provider-usage": () => ({ source: "cc:provider-usage", generatedAt: iso(2),
      summary: { total: 2, available: 1, watching: 1, nearLimit: 0, blocked: 0, unknown: 0 }, providers: [], routing: [] }),
    "/api/command-centre/wiki-graph": () => ({ nodes: [], edges: [], pageCount: 1284, edgeCount: 5210, lastSync: iso(7200), truncated: false, source: "supabase" }),
    "/api/pi-ceo/health": () => ({ status: "ok", uptime_s: 3600, swarm_enabled: true, swarm_shadow: true }),
    "/api/pi-ceo/api/sessions": () => [
      { id: "s-ra7912a", repo: "CleanExpo/RestoreAssist", status: "running", started: Date.now() / 1000 - 840, last_phase: "build" },
      { id: "s-uni2531", repo: "CleanExpo/Unite-Group", status: "evaluating", started: Date.now() / 1000 - 360 },
      { id: "s-ra7887b", repo: "CleanExpo/Pi-Dev-Ops", status: "complete", started: Date.now() / 1000 - 5400 },
    ],
    "/api/pi-ceo/api/projects/health": () => [
      { project_id: "RestoreAssist", repo: "CleanExpo/RestoreAssist", overall_health: 86, scores: { security: 86 } },
      { project_id: "CARSI", repo: "CleanExpo/CARSI", overall_health: 61, scores: { security: 61 } },
      { project_id: "Synthex", repo: "CleanExpo/Synthex", overall_health: 100, scores: {} },
    ],
    "/api/pi-ceo/api/mission-control/live": () => ({ ts: iso(), active_sessions: [{ id: "s-ra7912a", repo: "CleanExpo/RestoreAssist", phase: "build", elapsed_s: 840 }],
      recent_completions: [{ id: "s-ra7887b", repo: "CleanExpo/Pi-Dev-Ops", completed_at: iso(1800), score: 9.1 }],
      throughput: { hourly: Array.from({ length: 24 }, (_, i) => (i * 7) % 5) }, queue: { urgent: 0, high: 2 } }),
    "/api/pi-ceo/api/idea-pipeline": () => ({ snapshot: { intake: "", north_star: "", awaiting: 1, packet: null, verdicts: [], go_required: true, executed: false },
      packets: [{ idea_id: "i1", text: "Contractor leaderboard for NRPG", source: "telegram", verdict: null, go_at: null, executed: false }] }),
    "/api/pi-ceo/api/pipelines": () => [],
  };
}

/** Pi-CEO backend down: the proxy's 200 placeholder, 503s and quiet-failure bodies (spec A3). */
export function backendDownResponses(): Record<string, () => { status: number; body: unknown; headers?: Record<string, string> }> {
  const proxyFallback = (body: unknown) => () => ({ status: 200, body, headers: { "X-Upstream-Status": "502" } });
  return {
    "/api/pi-ceo/health": proxyFallback({ status: "unreachable", swarm_enabled: false, swarm_shadow: false }),
    "/api/pi-ceo/api/sessions": proxyFallback([]),
    "/api/pi-ceo/api/projects/health": proxyFallback([]),
    "/api/pi-ceo/api/mission-control/live": proxyFallback({ ts: iso(), active_sessions: [], recent_completions: [], throughput: { hourly: [] } }),
    "/api/pi-ceo/api/idea-pipeline": proxyFallback({ snapshot: { awaiting: 0, packet: null } }),
    "/api/pi-ceo/api/pipelines": proxyFallback([]),
    "/api/mesh-fleet": () => ({ status: 503, body: { status: "unavailable", checkedAt: iso(), reason: "upstream unreachable" } }),
    "/api/model-fabric": () => ({ status: 503, body: { enabled: false, healthy: false, error: "Pi-CEO unavailable" } }),
    "/api/swarm-status": () => ({ status: 200, body: { state: "UNKNOWN", autonomous_prs_today: null, autonomous_prs_limit: null, green_merges: null, green_merges_target: null, last_pr_ts: null, last_pr_url: null } }),
    "/api/kill-switch": () => ({ status: 200, body: { error: "upstream unreachable", swarm_enabled_env: false, kill_switch_active: false, escalation_lock_active: false, panic_count_last_hour: 0, approver_allowlist: [], approver_totp_configured: [] } }),
    "/api/curator-proposals": () => ({ status: 200, body: { error: "upstream unreachable", total: 0, returned: 0, by_status: {}, proposals: [] } }),
    "/api/mesh-fleet/wall": () => ({ status: 200, body: { generated_at: iso(), banner: { red: 0, grey: 0 }, fleet: { status: "broken", reason: "SOURCE BROKEN — upstream unreachable", machines: [], others: [] }, stations: [] } }),
  };
}

const PREFIXES = ["/api/pi-ceo/", "/api/mesh-fleet", "/api/model-fabric", "/api/swarm-status", "/api/kill-switch", "/api/curator-proposals", "/api/command-centre/"];

/** Route every dashboard feed a board reads. Unlisted paths fall through to the dev server. */
export async function routeFeeds(page: Page, mode: "healthy" | "down"): Promise<void> {
  const healthy = healthyResponses();
  const down = backendDownResponses();
  await page.route((url) => PREFIXES.some((p) => url.pathname.startsWith(p)), async (route: Route) => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() !== "GET") return route.fallback();
    if (mode === "down" && down[path]) {
      const r = down[path]();
      return route.fulfill({ status: r.status, contentType: "application/json", headers: r.headers, body: JSON.stringify(r.body) });
    }
    const make = healthy[path];
    if (!make) return route.fallback();
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(make()) });
  });
}
