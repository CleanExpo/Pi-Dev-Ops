// UNI-2647 — the TypeScript contract for GET /api/mission-control/live.
//
// Source of truth is app/server/routes/mission_control.py (and
// mission_control_sessions.py). These names must stay equal to the keys that
// function actually emits. `hourly_24h` is not one of them. `actions` is a
// list of objects, not strings.

/** `hourly: null` = the session store could not be read; not 24 empty hours. */
export interface MCThroughput {
  hourly?: number[] | null;
}

export interface MCAction {
  component?: string;
  status?: string;
  ok?: boolean;
  observed?: boolean;
  owner?: string;
  severity?: string;
  next_action?: string;
  evidence_required?: string[];
  detail?: string | null;
}

export interface MCSession {
  id: string;
  repo?: string;
  phase?: string;
  status?: string;
  elapsed_s?: number;
  issue_id?: string | null;
  last_log_tail?: string;
}

export interface MCCompletion {
  id: string;
  repo?: string;
  branch?: string | null;
  score?: number | null;
  pr_url?: string | null;
  issue_id?: string | null;
  completed_at?: string | null;
}

/**
 * `available: false` means the Linear read failed: counts are null and `error`
 * says why. Render UNAVAILABLE, never 0 — zero urgent is a measurement.
 */
export interface MCQueue {
  available?: boolean;
  error?: string | null;
  urgent?: number | null;
  high?: number | null;
  next_issue_id?: string | null;
  next_issue_title?: string | null;
}

/** Same rule as MCQueue: `available: false` is unknown, not a silent day. */
export interface MCPulse {
  available?: boolean;
  error?: string | null;
  last_at?: string | null;
  comments_today?: number | null;
  pulse_issue_id?: string | null;
}

export interface MCObservability {
  source?: string;
  ok?: boolean;
  fully_observed?: boolean;
  red_components?: string[];
  degraded_components?: string[];
  actions?: MCAction[];
}

/** RA-7539 — fail-closed synthetic status. Unregistered must never look ready. */
export interface MCNexusOne {
  lineage: "SYNTHETIC";
  excluded_from_real_acceptance: true;
  registered: boolean;
  ready: false;
  shipped: false;
  worker_enrolled?: boolean;
  max_subscription_only?: boolean;
  windows_policy?: string;
}

/** Audit #17 — nightly ticket sweeper counts. `counts: null` means never run, not zero. */
export interface MCSweeperCounts {
  stale_labelled: number;
  stale_to_todo: number;
  review_red_pr: number;
  review_unknown: number;
  failed_to_ready: number;
  failed_to_blocked: number;
}

export interface MCTicketSweeper {
  last_run_at: string | null;
  dry_run: boolean;
  complete: boolean;
  counts: MCSweeperCounts | null;
  review_red_pr?: string[];
  errors: string[];
}

export interface MissionControlLive {
  ts?: string;
  error?: string;
  throughput?: MCThroughput;
  /** null = the session store could not be read; [] = read, nothing running. */
  active_sessions?: MCSession[] | null;
  recent_completions?: MCCompletion[] | null;
  queue?: MCQueue;
  idea_pipeline?: {
    awaiting?: number;
    packet?: { idea_id?: string; text?: string; status?: string } | null;
  };
  pulse?: MCPulse;
  observability?: MCObservability;
  nexus_one?: MCNexusOne;
  ticket_sweeper?: MCTicketSweeper;
}

/** Why a queue/pulse section could not be read, or null when it was read. */
export function unavailableReason(section: { available?: boolean; error?: string | null } | null | undefined): string | null {
  if (!section) return "not reported by the backend";
  return section.available === false ? section.error || "read failed" : null;
}

/** Sum of the 24 hourly buckets the backend sends as `throughput.hourly`. */
export function completed24h(hourly: readonly number[] | undefined | null): number {
  return (hourly ?? []).reduce((acc, n) => acc + (n || 0), 0);
}
