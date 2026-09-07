import { describe, expect, it } from "vitest";
import {
  CHILD_TICKETS_NOTE,
  CONTROL_GOAL_CTA,
  HOW_TO_GET_THE_GOAL,
  LINEAR_DEST_NOTE,
  TWO_PROJECTS_NOTE,
  analyzeProgress,
  analyzingCopy,
} from "@/lib/control/goalCopy";

describe("Goal copy", () => {
  it("names the same Goal path on the hub button and the Goal page", () => {
    expect(CONTROL_GOAL_CTA).toBe("Goal → Linear");
  });

  it("names the Linear destination and that sub-tasks become children", () => {
    expect(LINEAR_DEST_NOTE).toContain("CleanExpo/Pi-Dev-Ops");
    expect(LINEAR_DEST_NOTE).toContain("Backlog");
    expect(CHILD_TICKETS_NOTE.toLowerCase()).toContain("child");
    expect(TWO_PROJECTS_NOTE).toContain("top bar");
  });

  it("teaches the operator how to get the full goal, and keeps Analyze off Linear", () => {
    expect(HOW_TO_GET_THE_GOAL.length).toBeGreaterThanOrEqual(7);
    expect(HOW_TO_GET_THE_GOAL.join(" ")).toContain("stranger");
    expect(analyzingCopy(3)).toContain("Linear is not written");
    expect(analyzeProgress(35)).toBe(50);
  });
});
