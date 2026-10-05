// RA-7898 — builds by stage, from the shared `sessions` feed. Pure: no fetch.

import { parseOperatorSessions, sessionTime, type OperatorSession } from "@/lib/operator-status";

export const STAGES = ["Queued", "Building", "Checking", "Done", "Stopped"] as const;
export type Stage = (typeof STAGES)[number];

const STOPPED = new Set(["failed", "killed", "blocked", "stalled", "interrupted", "error"]);
const DONE = new Set(["complete", "completed", "done", "shipped"]);
const QUEUED = new Set(["queued", "pending", "created", "waiting"]);
const CHECKING = new Set(["evaluating", "evaluation", "checking", "reviewing"]);

export function stageOf(status: string): Stage {
  const s = status.toLowerCase();
  if (DONE.has(s)) return "Done";
  if (STOPPED.has(s)) return "Stopped";
  if (QUEUED.has(s)) return "Queued";
  if (CHECKING.has(s)) return "Checking";
  return "Building";
}

export interface BuildRow extends OperatorSession {
  stage: Stage;
  startedMs: number;
}

/** Null when the payload is not a session list — never an empty board. */
export function buildRows(value: unknown): BuildRow[] | null {
  const sessions = parseOperatorSessions(value);
  if (!sessions) return null;
  return sessions
    .map((s) => ({ ...s, stage: stageOf(s.status), startedMs: sessionTime(s.started) }))
    .sort((a, b) => b.startedMs - a.startedMs);
}

export function runningCount(rows: readonly BuildRow[]): number {
  return rows.filter((r) => r.stage === "Building" || r.stage === "Checking").length;
}
