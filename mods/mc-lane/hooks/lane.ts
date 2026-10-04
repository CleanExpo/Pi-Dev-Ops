// Pure helpers for mc-lane: no `$`, so they unit-test without the kit.
//
// WHAT IS SENT. Only names, numbers and booleans. A tool call's input and output
// never leave the machine — not even redacted — so there is nothing to redact on
// the server and nothing a leaked row can expose. The server re-validates every
// field (app/server/routes/mesh_lane_events.py); this file is the first gate,
// not the only one.

export type LaneEventKind = 'session_start' | 'tool' | 'usage' | 'session_end'

export type LaneEvent = {
  session_id: string
  seq: number
  kind: LaneEventKind
  at: string
  repo?: string
  model?: string
  tool?: string
  ok?: boolean
  ms?: number
  ctx_pct?: number
  rate_pct?: number
  cost_usd?: number
}

/** Hard cap on one POST; the server refuses more (MAX_BATCH there). */
export const MAX_BATCH = 200

/** Hard cap on what a lane holds while the backend is unreachable. Oldest go first. */
export const MAX_QUEUE = 2000

const TOOL_NAME = /^[A-Za-z0-9_.:-]{1,128}$/

/**
 * A tool's name as Mission Control may show it. MCP tool names carry the server
 * name, which is configuration, not content, so they pass; anything that does
 * not look like a name is replaced rather than sent.
 */
export function toolName(raw: unknown): string {
  return typeof raw === 'string' && TOOL_NAME.test(raw) ? raw : 'unknown'
}

/** `owner/name` from a git remote URL, or undefined. Never sends the URL itself (it can hold a token). */
export function repoSlug(remote: string | null | undefined): string | undefined {
  if (!remote) return undefined
  const m = /[:/]([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+?)(?:\.git)?\/?$/.exec(remote.trim())
  return m ? `${m[1]}/${m[2]}` : undefined
}

/** Highest rate-limit window used, 0–100, or undefined when none reported. */
export function worstRate(limits: readonly { percentUsed: number }[] | undefined): number | undefined {
  if (!limits || limits.length === 0) return undefined
  return Math.max(...limits.map(l => l.percentUsed))
}

/**
 * Sequence numbers are milliseconds × 1000 plus a counter, so they stay
 * increasing across a module reload (which resets module variables) and the
 * server's unique (session_id, seq) never drops a new event as a duplicate.
 */
export function makeSeq(nowMs: number, counter: number): number {
  return Math.floor(nowMs) * 1000 + (counter % 1000)
}

/** Appends and trims to MAX_QUEUE, dropping the oldest. Returns how many were dropped. */
export function enqueue(queue: LaneEvent[], ev: LaneEvent): number {
  queue.push(ev)
  const over = queue.length - MAX_QUEUE
  if (over > 0) queue.splice(0, over)
  return Math.max(over, 0)
}

/** Drops what the server acknowledged: every event of a session at or below its acked seq. */
export function dropAcked(queue: LaneEvent[], acked: Record<string, number>): LaneEvent[] {
  return queue.filter(ev => !(ev.session_id in acked && ev.seq <= acked[ev.session_id]))
}
