// RA-7898 — payload checks for the Pi-CEO proxy feeds.
//
// Same rule as validate.ts: a 200 is live only when every row and field its
// panels read is present in the type they read it as. Each check mirrors the
// TypeScript contract the panels already use (lib/control/mission-control-
// live.ts, lib/control/project-pathway.ts, lib/control/idea-pipeline.ts,
// lib/operator-status.ts), which follows what the backend emits.

import { parseOperatorHealth, parseOperatorSessions } from "@/lib/operator-status";
import { record } from "./http";

type Row = Record<string, unknown>;
const isText = (v: unknown) => typeof v === "string";
const isNum = (v: unknown) => typeof v === "number" && Number.isFinite(v);
const isBool = (v: unknown) => typeof v === "boolean";
const optText = (v: unknown) => v === undefined || v === null || isText(v);
const optNum = (v: unknown) => v === undefined || v === null || isNum(v);
const optBool = (v: unknown) => v === undefined || isBool(v);
const isTextList = (v: unknown) => Array.isArray(v) && v.every(isText);
const optTextList = (v: unknown) => v === undefined || isTextList(v);
const rows = (v: unknown, check: (r: Row) => boolean) =>
  Array.isArray(v) && v.every((x) => { const r = record(x); return r !== null && check(r); });
const optRecord = (v: unknown, check: (r: Row) => boolean) => {
  if (v === undefined || v === null) return true;
  const r = record(v);
  return r !== null && check(r);
};
const valuesAre = (v: unknown, check: (x: unknown) => boolean) => {
  if (v === undefined) return true;
  const r = record(v);
  return r !== null && Object.values(r).every(check);
};

const isSession = (s: Row) => isText(s.id) && optText(s.repo) && optText(s.phase) && optText(s.status)
  && optNum(s.elapsed_s) && optText(s.issue_id) && optText(s.last_log_tail);
const isCompletion = (c: Row) => isText(c.id) && optText(c.repo) && optText(c.branch) && optNum(c.score)
  && optText(c.pr_url) && optText(c.issue_id) && optText(c.completed_at);
const isQueue = (q: Row) => isNum(q.urgent) && isNum(q.high) && optText(q.next_issue_id) && optText(q.next_issue_title);
const isPulse = (p: Row) => optText(p.last_at) && optNum(p.comments_today) && optText(p.pulse_issue_id);
const isAction = (a: Row) => optText(a.component) && optText(a.status) && optBool(a.ok) && optBool(a.observed)
  && optText(a.owner) && optText(a.severity) && optText(a.next_action) && optTextList(a.evidence_required) && optText(a.detail);
const isObservability = (o: Row) => optText(o.source) && optBool(o.ok) && optBool(o.fully_observed)
  && optTextList(o.red_components) && optTextList(o.degraded_components)
  && (o.actions === undefined || rows(o.actions, isAction));
const isHudSession = (s: Row) => isText(s.session_id) && optText(s.project) && optText(s.stage)
  && optNum(s.pct) && optNum(s.used_tokens) && optNum(s.window) && isNum(s.age_s);
const isHud = (h: Row) => {
  const counts = record(h.counts);
  return isBool(h.available) && optText(h.reason) && isText(h.checked_dir) && rows(h.sessions, isHudSession)
    && counts !== null && isNum(counts.live) && isNum(counts.handoff) && isNum(counts.hard);
};

/** mission-control/live: routes/mission_control.py always sends the first six. */
export function isMissionControlLive(b: Row): boolean {
  const throughput = record(b.throughput);
  return isText(b.ts) && throughput !== null && Array.isArray(throughput.hourly) && throughput.hourly.every(isNum)
    && rows(b.active_sessions, isSession) && rows(b.recent_completions, isCompletion)
    && optRecord(b.queue, isQueue) && b.queue !== undefined && b.queue !== null
    && optRecord(b.pulse, isPulse) && b.pulse !== undefined && b.pulse !== null
    && optRecord(b.observability, isObservability) && optRecord(b.claude_hud, isHud);
}

/**
 * projects/health: scanner.get_health_summary always sends all six fields; a
 * project with no scans yet is `scores: {}` and `overall_health: 100`, never
 * absent fields. HealthGrid averages overall_health and walks scores.
 */
const isMap = (v: unknown, check: (x: unknown) => boolean) => v !== undefined && valuesAre(v, check);
export const isProjectList = (v: unknown) => rows(v, (p) => isText(p.project_id) && isText(p.repo)
  && isNum(p.overall_health) && isMap(p.scores, isNum) && isMap(p.findings_count, isNum)
  && isMap(p.deployments, isText));

/** pipelines: PipelineSummary rows. */
export const isPipelineList = (v: unknown) => rows(v, (p) => isText(p.pipeline_id) && isText(p.repo_url)
  && isText(p.current_phase) && isTextList(p.phases_completed) && isText(p.updated_at));

const nested = (v: unknown, check: (r: Row) => boolean) => { const r = record(v); return r !== null && check(r); };
const isPacket = (p: Row) => isText(p.idea_id) && isText(p.text) && isText(p.status) && optText(p.verdict)
  && isText(p.recommended_verdict) && optText(p.go_at) && isBool(p.executed)
  && nested(p.north_star_fit, (n) => isText(n.label) && optNum(n.score) && n.score !== undefined && isText(n.rationale) && optText(n.source_revision))
  && nested(p.effort_vs_impact, (n) => isText(n.effort) && isText(n.impact) && isText(n.rationale))
  && nested(p.directive, (n) => isText(n.label) && isText(n.rationale))
  && nested(p.displacement, (n) => isText(n.would_displace) && isText(n.rationale))
  && nested(p.judge, (n) => optNum(n.score) && n.score !== undefined && isText(n.decision) && optText(n.note))
  && nested(p.spm, (n) => isText(n.problem) && isText(n.desired_outcome) && isText(n.out_of_scope));

/** idea-pipeline: IdeaPipelinePayload. */
export function isIdeaPipeline(v: unknown): boolean {
  const body = record(v);
  const s = record(body?.snapshot);
  return s !== null && isText(s.intake) && isText(s.north_star) && isNum(s.awaiting)
    && (s.packet === null || optRecord(s.packet, isPacket) && s.packet !== undefined) && isTextList(s.verdicts) && isBool(s.go_required) && isBool(s.executed)
    && (body?.packets === undefined || rows(body.packets, isPacket));
}

/** /health and /api/sessions: the parsers the operator panels already use. */
export const isHealth = (v: unknown) => parseOperatorHealth(v) !== null;
export const isSessionList = (v: unknown) => parseOperatorSessions(v) !== null;
