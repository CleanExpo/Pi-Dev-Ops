// RA-7898 A6 — the routed responses both servers get in boards-unchanged.spec.ts.
// Synthetic test fixtures, never shipped. Kept free of Playwright imports so
// __tests__/boards-a6-feeds.test.ts can hold every body to the head's feed
// validators: a body the head rejects would make A6 compare an error panel.
export const FROZEN = new Date("2026-10-03T00:00:00Z");

const iso = (agoS = 0) => new Date(FROZEN.getTime() - agoS * 1000).toISOString();
export const A6_FEEDS: Record<string, unknown> = {
  "/api/mesh-fleet": { status: "ok", checkedAt: iso(), machines: [{ host: "Phill_Desktop", revision: "e3dff5e", lastHeartbeat: iso(8), currentClaim: "RA-7898", stale: false }] },
  "/api/mesh-fleet/wall": { generated_at: iso(1), banner: { red: 0, grey: 7 }, fleet: { status: "ok", reason: "", others: [], machines: [] },
    stations: ["Capture", "Shape", "Contract", "Build", "Prove", "Ship", "Learn"].map((name) => ({ id: name.toLowerCase(), name, chip: "GREY", reason: "NO LIVE SOURCE YET" })) },
  "/api/model-fabric": { enabled: true, healthy: true, models_available: 3, totals: { calls: 10, failures: 1, fallbacks: 0, strengthened: 0 }, lanes: { review: { model: "m3", banned: false } } },
  "/api/swarm-status": { state: "SHADOW", autonomous_prs_today: 1, autonomous_prs_limit: 3, green_merges: 4, green_merges_target: 20, last_pr_ts: null, last_pr_url: null },
  "/api/kill-switch": { swarm_enabled_env: true, kill_switch_active: false, escalation_lock_active: false, panic_count_last_hour: 0, approver_allowlist: ["a", "b"], approver_totp_configured: ["a"] },
  "/api/curator-proposals": { total: 0, returned: 0, by_status: {}, proposals: [] },
  "/api/pi-ceo/health": { status: "ok", uptime_s: 3600, swarm_enabled: true, swarm_shadow: true },
  "/api/pi-ceo/api/sessions": [{ id: "s1", repo: "CleanExpo/RA", status: "running", started: FROZEN.getTime() / 1000 - 600 }],
  "/api/pi-ceo/api/projects/health": [{ project_id: "RA", repo: "CleanExpo/RA", overall_health: 86, scores: { security: 86 }, findings_count: {}, deployments: {} }],
  "/api/pi-ceo/api/mission-control/live": { ts: iso(), active_sessions: [], recent_completions: [], throughput: { hourly: [1, 2, 3] },
    queue: { urgent: 0, high: 0 }, pulse: { last_at: null, comments_today: 0, pulse_issue_id: null } },
  "/api/pi-ceo/api/pipelines": [],
  "/api/pi-ceo/api/idea-pipeline": { snapshot: { intake: "", north_star: "", awaiting: 0, packet: null, verdicts: [], go_required: true, executed: false } },
};
