// Presentation helpers for the routine run tracker (RA-1011).
//
// Extracted from app/(main)/routines/page.tsx when that file was edited, per
// the CLAUDE.md file-length convention: the page is over the 300-line
// convention and grandfathered, so touching it means extracting rather than
// adding. Pure formatting — no state, no fetching, no React.
import { brisbaneDateTime, brisbaneTime } from "@/lib/brisbane-time";

export const STATUS_COLOR: Record<string, string> = {
  success: "#4ADE80",
  failure: "#F87171",
  timeout: "#FFD166",
};

export const STATUS_ICON: Record<string, string> = {
  success: "✓",
  failure: "✗",
  timeout: "⏱",
};

export const ROUTINES_LIST_NOTE =
  "Cron outcomes — same list as Control → Runs.";

export const TRIGGER_LABEL: Record<string, string> = {
  api:      "API",
  schedule: "Sched",
  github:   "GitHub",
};

export function fmtDuration(s: number): string {
  if (s < 60) return `${Math.round(s)}s`;
  const m = Math.floor(s / 60);
  const rem = Math.round(s % 60);
  return rem > 0 ? `${m}m ${rem}s` : `${m}m`;
}

/** Last-refresh stamp for the page header, Brisbane time with seconds. */
export function fmtClock(ms: number): string {
  return brisbaneTime(ms, true);
}

export function fmtTs(ts: string): string {
  if (!ts) return "—";
  try {
    return brisbaneDateTime(ts);
  } catch {
    return ts;
  }
}

export function repoShort(repo: string): string {
  return repo.split("/").slice(-1)[0] ?? repo;
}
