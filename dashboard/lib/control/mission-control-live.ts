// UNI-2647 — the TypeScript contract for GET /api/mission-control/live.
//
// Source of truth is app/server/routes/mission_control.py (and
// mission_control_sessions.py). These names must stay equal to the keys that
// function actually emits. `hourly_24h` is not one of them. `actions` is a
// list of objects, not strings.

export interface MCThroughput {
  hourly?: number[];
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

export interface MCQueue {
  urgent?: number;
  high?: number;
  next_issue_id?: string | null;
  next_issue_title?: string;
}

export interface MCPulse {
  last_at?: string | null;
  comments_today?: number;
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

export interface MissionControlLive {
  ts?: string;
  error?: string;
  throughput?: MCThroughput;
  active_sessions?: MCSession[];
  recent_completions?: MCCompletion[];
  queue?: MCQueue;
  pulse?: MCPulse;
  observability?: MCObservability;
}

/** Sum of the 24 hourly buckets the backend sends as `throughput.hourly`. */
export function completed24h(hourly: readonly number[] | undefined | null): number {
  return (hourly ?? []).reduce((acc, n) => acc + (n || 0), 0);
}
