// RA-7898 — shared helpers for the feed reader tests (not a test file).
import { vi } from "vitest";

export const signal = new AbortController().signal;

export function serve(body: unknown, status = 200, headers: Record<string, string> = {}) {
  const fn = vi.fn(async (_url: string) => new Response(JSON.stringify(body), { status, headers }));
  vi.stubGlobal("fetch", fn);
  return fn;
}
export function fail(message = "network down") {
  vi.stubGlobal("fetch", vi.fn(async () => { throw new Error(message); }));
}

// Complete payloads, in the shape the backend always sends (routes/swarm.py,
// routes/mission_control.py). Tests drop one field at a time from these.
export const KILL_SWITCH = {
  swarm_enabled_env: true, kill_switch_active: false, escalation_lock_active: false,
  panic_count_last_hour: 0, approver_allowlist: ["a"], approver_totp_configured: ["a"],
};
export const MC_LIVE = {
  ts: "2026-10-03T00:00:00Z", throughput: { hourly: [] }, active_sessions: [], recent_completions: [],
  queue: { urgent: 0, high: 0 }, pulse: { last_at: null, comments_today: 0, pulse_issue_id: null },
};
export const SWARM = {
  state: "ACTIVE", autonomous_prs_today: 1, autonomous_prs_limit: 3, green_merges: null,
  green_merges_target: null, last_pr_ts: null, last_pr_url: null,
};
export const FABRIC = {
  enabled: true, healthy: true, models_available: 4, lanes: {},
  totals: { calls: 10, failures: 1, fallbacks: 0, strengthened: 0 },
};
export const without = (body: Record<string, unknown>, key: string) => Object.fromEntries(Object.entries(body).filter(([k]) => k !== key));
