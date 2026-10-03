// RA-7898 — shared types for the boards sources layer.
//
// A feed is one URL read on one interval. Every feed resolves to exactly one
// of five states (docs/specs/modular-boards.md §3.2); the panel-shaped `value`
// of the latest read travels beside it so converted panels keep their own
// rendering rules unchanged.

export type SourceState = "loading" | "live" | "stale" | "unreachable" | "no_source";

/** What one read concluded. `value` is shaped for the panel that consumes it. */
export interface FeedRead<T> {
  kind: "live" | "unreachable" | "no_source";
  value: T;
  /** Human-readable cause when kind is not live. */
  reason?: string;
  /** Server-side timestamp of the data, when the payload carries one. */
  serverTs?: string | number | null;
  /** HTTP status of the response, when one arrived. */
  httpStatus?: number | null;
}

export interface FeedDef<T> {
  id: string;
  /** The URL as requested on the wire (documentation and the tap). */
  url: string;
  intervalMs: number;
  read: (signal: AbortSignal) => Promise<FeedRead<T>>;
  /** True when the server timestamp is the freshness authority. */
  serverClock?: boolean;
  /** Local feeds (clock, static text) never touch the network. */
  local?: boolean;
}

export interface SourceSnapshot<T> {
  id: string;
  state: SourceState;
  /** Increments once per finished read. 0 = nothing has finished yet. */
  seq: number;
  /** Panel-shaped value of the latest finished read (null before the first). */
  value: T | null;
  /** Value of the latest read that was live. */
  lastGood: T | null;
  reason: string | null;
  httpStatus: number | null;
  /** Browser time the latest read finished. */
  fetchedAt: number | null;
  /** Browser time of the latest live read. */
  lastGoodAt: number | null;
  /** Server timestamp of the latest live read, as epoch ms. */
  serverTs: number | null;
}

/** Ordering used to combine several sources into one module state. Worst first. */
export const STATE_SEVERITY: readonly SourceState[] = ["unreachable", "no_source", "stale", "loading", "live"];

export function worstState(states: readonly SourceState[]): SourceState {
  if (states.length === 0) return "no_source";
  return [...states].sort((a, b) => STATE_SEVERITY.indexOf(a) - STATE_SEVERITY.indexOf(b))[0];
}

/** Stale age: three intervals, never under 15 s (spec §3.2). */
export function staleAfterMs(intervalMs: number): number {
  return Math.max(15_000, intervalMs * 3);
}

/** Parse an ISO string or epoch (seconds or ms) into epoch ms; null when unusable. */
export function toEpochMs(ts: string | number | null | undefined): number | null {
  if (ts === null || ts === undefined || ts === "") return null;
  if (typeof ts === "number") return Number.isFinite(ts) ? (ts < 1e12 ? ts * 1000 : ts) : null;
  const ms = Date.parse(ts);
  return Number.isNaN(ms) ? null : ms;
}
