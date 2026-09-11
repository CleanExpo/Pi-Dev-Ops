import { describe, expect, it } from "vitest";
import {
  WATCH_EMPTY_NOTE,
  idleSessionsNote,
  nothingAuthorized,
  watchBuildsHref,
  watchLoopHref,
  watchSwarmHref,
} from "@/lib/control/watchWork";

describe("watch the work", () => {
  it("treats an empty queue and no sessions as unauthorized idle", () => {
    const idle = { sessionCount: 0, urgent: 0, high: 0, nextIssueId: null };
    expect(nothingAuthorized(idle)).toBe(true);
    expect(idleSessionsNote(idle)).toBe(WATCH_EMPTY_NOTE);
    expect(WATCH_EMPTY_NOTE).toContain("Ready for Pi-Dev");
    expect(WATCH_EMPTY_NOTE).toContain("pi-dev:autonomous");
  });

  it("keeps a queued ticket distinct from unauthorized idle", () => {
    const queued = { sessionCount: 0, urgent: 0, high: 1, nextIssueId: "RA-1" };
    expect(nothingAuthorized(queued)).toBe(false);
    expect(idleSessionsNote(queued)).toContain("Loop");
  });

  it("points at Builds, Swarm, and Loop — not a write action", () => {
    expect(watchBuildsHref()).toBe("/builds");
    expect(watchSwarmHref()).toBe("/control/swarm");
    expect(watchLoopHref()).toBe("/loop");
  });
});
