import { describe, expect, it } from "vitest";
import {
  WATCH_EMPTY_NOTE,
  asWatchInput,
  idleSessionsNote,
  nothingAuthorized,
  watchBuildsHref,
  watchGoalHref,
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

  it("treats blank next-issue ids and missing counts as unauthorized idle", () => {
    expect(nothingAuthorized(asWatchInput({
      sessionCount: undefined,
      urgent: null,
      high: 0,
      nextIssueId: "   ",
    }))).toBe(true);
    expect(idleSessionsNote({ nextIssueId: "  RA-9  ", high: 0, urgent: 0, sessionCount: 0 }))
      .toContain("Loop");
  });

  it("never treats a running session as unauthorized idle", () => {
    expect(nothingAuthorized(asWatchInput({ sessionCount: 1, urgent: 0, high: 0, nextIssueId: null }))).toBe(false);
  });

  it("points at Builds, Swarm, and Loop — not a write action", () => {
    expect(watchBuildsHref()).toBe("/builds");
    expect(watchSwarmHref()).toBe("/control/swarm");
    expect(watchLoopHref()).toBe("/loop");
    expect(watchGoalHref()).toBe("/control/goal");
  });
});
