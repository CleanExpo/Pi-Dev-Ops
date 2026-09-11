export const WATCH_EMPTY_NOTE =
  "Nothing authorized is running. Tickets wait in Backlog until Ready for Pi-Dev and pi-dev:autonomous.";

export const WATCH_QUEUE_NOTE =
  "No session yet. The poller waits for the next tick. Open Loop for the queue.";

export const WATCH_BUILDS = "Builds";
export const WATCH_SWARM = "Swarm";
export const WATCH_LOOP = "Loop";
export const WATCH_GOAL = "Goal";

export function asWatchInput(raw: {
  sessionCount?: number | null;
  urgent?: number | null;
  high?: number | null;
  nextIssueId?: string | null;
}): {
  sessionCount: number;
  urgent: number;
  high: number;
  nextIssueId: string | null;
} {
  const next = raw.nextIssueId?.trim() || null;
  return {
    sessionCount: Math.max(0, Number(raw.sessionCount) || 0),
    urgent: Math.max(0, Number(raw.urgent) || 0),
    high: Math.max(0, Number(raw.high) || 0),
    nextIssueId: next,
  };
}

export function nothingAuthorized(input: {
  sessionCount: number;
  urgent: number;
  high: number;
  nextIssueId: string | null;
}): boolean {
  const n = asWatchInput(input);
  return n.sessionCount === 0 && n.urgent === 0 && n.high === 0 && !n.nextIssueId;
}

export function watchBuildsHref(): string {
  return "/builds";
}

export function watchSwarmHref(): string {
  return "/control/swarm";
}

export function watchLoopHref(): string {
  return "/loop";
}

export function watchGoalHref(): string {
  return "/control/goal";
}

export function idleSessionsNote(input: {
  sessionCount?: number | null;
  urgent?: number | null;
  high?: number | null;
  nextIssueId?: string | null;
}): string {
  const n = asWatchInput(input);
  if (nothingAuthorized(n)) return WATCH_EMPTY_NOTE;
  return WATCH_QUEUE_NOTE;
}
