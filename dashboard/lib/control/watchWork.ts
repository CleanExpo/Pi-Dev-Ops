export const WATCH_EMPTY_NOTE =
  "Nothing authorized is running. Tickets wait in Backlog until Ready for Pi-Dev and pi-dev:autonomous.";

export const WATCH_QUEUE_NOTE =
  "No session yet. The poller waits for the next tick. Open Loop for the queue.";

export const WATCH_BUILDS = "Builds";
export const WATCH_SWARM = "Swarm";
export const WATCH_LOOP = "Loop";

export function nothingAuthorized(input: {
  sessionCount: number;
  urgent: number;
  high: number;
  nextIssueId: string | null;
}): boolean {
  return (
    input.sessionCount === 0 &&
    input.urgent === 0 &&
    input.high === 0 &&
    !input.nextIssueId
  );
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

export function idleSessionsNote(input: {
  sessionCount: number;
  urgent: number;
  high: number;
  nextIssueId: string | null;
}): string {
  if (nothingAuthorized(input)) return WATCH_EMPTY_NOTE;
  return WATCH_QUEUE_NOTE;
}
