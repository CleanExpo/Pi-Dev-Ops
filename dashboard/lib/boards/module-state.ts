// RA-7898 — combine a module's sources into one frame state (spec §3.2).

import { FEEDS } from "./sources/feeds";
import { worstState, type SourceSnapshot, type SourceState } from "./sources/types";

export interface ModuleStatus {
  state: SourceState;
  reason: string | null;
  /** Epoch ms of the freshest proof the data is current, or null. */
  freshAt: number | null;
  /** Which clock `freshAt` comes from. */
  clock: "server" | "browser" | "local" | null;
  /** True when one of the sources answered 401. */
  signedOut: boolean;
}

export const STATE_LABEL: Record<SourceState, string> = {
  loading: "Loading",
  live: "Live",
  stale: "Stale",
  unreachable: "Unreachable",
  no_source: "No source yet",
};

export function moduleStatus(snaps: readonly SourceSnapshot<unknown>[]): ModuleStatus {
  const state = worstState(snaps.map((s) => s.state));
  const worst = snaps.filter((s) => s.state === state);
  const reason = worst.map((s) => s.reason).find((r): r is string => Boolean(r)) ?? null;
  const local = snaps.length > 0 && snaps.every((s) => FEEDS.get(s.id)?.local);
  // The oldest of the sources' freshness is the module's freshness.
  const stamps = snaps.map((s) => (FEEDS.get(s.id)?.serverClock && s.serverTs !== null ? s.serverTs : s.lastGoodAt));
  const known = stamps.filter((t): t is number => t !== null);
  const freshAt = known.length === snaps.length && known.length > 0 ? Math.min(...known) : null;
  const server = snaps.some((s) => FEEDS.get(s.id)?.serverClock && s.serverTs !== null);
  return {
    state,
    reason,
    freshAt: local ? null : freshAt,
    clock: local ? "local" : freshAt === null ? null : server ? "server" : "browser",
    signedOut: snaps.some((s) => s.httpStatus === 401),
  };
}
