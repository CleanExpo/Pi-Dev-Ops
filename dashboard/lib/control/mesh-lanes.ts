/**
 * Server-side projection of GET /api/mesh/lane-events for the "Claude lanes" module.
 *
 * The events come from the mc-lane Claude Code mod (mods/mc-lane): names,
 * numbers and booleans only — no tool input or output ever reaches the
 * backend. This module folds the newest events into one row per session.
 *
 * Honesty rules (RA-1109, UNI-2412):
 *   - A failed or malformed read is `unavailable`, never an empty lane list.
 *   - Cost the lane did not report is `null` and is shown as "unknown", never $0.
 *   - Counts cover only the events read (`windowEvents`), and say so.
 */

export interface LaneRow {
  sessionId: string;
  host: string;
  repo: string | null;
  model: string | null;
  /** Newest event's server receive time (ISO), or the lane's own clock when absent. */
  lastAt: string | null;
  ended: boolean;
  toolCalls: number;
  toolFails: number;
  lastTool: string | null;
  ctxPct: number | null;
  ratePct: number | null;
  costUsd: number | null;
}

export interface LanesOk {
  status: "ok";
  checkedAt: string;
  /** How many events the rows were folded from (newest first, capped upstream). */
  windowEvents: number;
  lanes: LaneRow[];
}

export interface LanesUnavailable {
  status: "unavailable";
  checkedAt: string;
  reason: string;
}

export type LanesView = LanesOk | LanesUnavailable;

export function unavailableLanes(reason: string, checkedAt: string): LanesUnavailable {
  return { status: "unavailable", checkedAt, reason };
}

const str = (v: unknown): string | null => (typeof v === "string" && v !== "" ? v : null);
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

function newer(a: string | null, b: string | null): boolean {
  if (b === null) return a !== null;
  if (a === null) return false;
  return Date.parse(a) > Date.parse(b);
}

export function projectLanes(raw: unknown, checkedAt: string): LanesView {
  const body = raw !== null && typeof raw === "object" && !Array.isArray(raw) ? (raw as Record<string, unknown>) : null;
  if (!body || !Array.isArray(body.events)) return unavailableLanes("invalid lane-events payload", checkedAt);

  const rows = new Map<string, LaneRow & { usageAt: string | null; toolAt: string | null }>();
  for (const item of body.events) {
    if (item === null || typeof item !== "object") continue;
    const ev = item as Record<string, unknown>;
    const sessionId = str(ev.session_id);
    if (!sessionId) continue;
    const at = str(ev.received_at) ?? str(ev.at);
    let row = rows.get(sessionId);
    if (!row) {
      row = {
        sessionId, host: str(ev.host) ?? "unknown", repo: null, model: null, lastAt: null, ended: false,
        toolCalls: 0, toolFails: 0, lastTool: null, ctxPct: null, ratePct: null, costUsd: null,
        usageAt: null, toolAt: null,
      };
      rows.set(sessionId, row);
    }
    if (newer(at, row.lastAt)) row.lastAt = at;
    switch (ev.kind) {
      case "session_start":
        row.repo = row.repo ?? str(ev.repo);
        row.model = row.model ?? str(ev.model);
        break;
      case "session_end":
        row.ended = true;
        break;
      case "tool":
        row.toolCalls += 1;
        if (ev.ok === false) row.toolFails += 1;
        if (newer(at, row.toolAt)) { row.toolAt = at; row.lastTool = str(ev.tool); }
        break;
      case "usage":
        if (newer(at, row.usageAt)) {
          row.usageAt = at;
          row.ctxPct = num(ev.ctx_pct);
          row.ratePct = num(ev.rate_pct);
          row.costUsd = num(ev.cost_usd);
        }
        break;
      default:
        break;
    }
  }

  const lanes: LaneRow[] = [...rows.values()]
    .map(({ usageAt: _u, toolAt: _t, ...row }) => row)
    .sort((a, b) => Number(a.ended) - Number(b.ended) || (Date.parse(b.lastAt ?? "") || 0) - (Date.parse(a.lastAt ?? "") || 0));
  return { status: "ok", checkedAt, windowEvents: body.events.length, lanes };
}
