import { describe, expect, it } from "vitest";
import {
  BRIEFS_EMPTY_NOTE,
  BRIEFS_LOAD_FAIL_NOTE,
  CHILD_TICKETS_NOTE,
  CONTROL_GOAL_CTA,
  FALLBACK_DRAFT_NOTE,
  HOW_TO_GET_THE_GOAL,
  LESS_ANALYSIS,
  MORE_ANALYSIS,
  LINEAR_DEST_NOTE,
  TWO_PROJECTS_NOTE,
  analyzeProgress,
  analyzingCopy,
  nextAnalyzeHint,
  nextSaveBriefHint,
  nextWriteHint,
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

  it("names the next action when Analyze, Save brief, or Write is blocked", () => {
    expect(nextAnalyzeHint("goal long enough", "acceptance long enough", "")).toContain("Create brief");
    expect(nextAnalyzeHint("short", "acceptance long enough", "brief-1")).toContain("Write the goal");
    expect(nextAnalyzeHint("goal long enough", "short", "brief-1")).toContain("Write acceptance");
    expect(nextSaveBriefHint({ title: "", description: "", audience: "" })).toContain("product name");
    expect(nextWriteHint([])).toContain("Select at least one ticket");
    expect(FALLBACK_DRAFT_NOTE).toContain("fallback");
    expect(BRIEFS_EMPTY_NOTE).toContain("Create brief");
    expect(BRIEFS_LOAD_FAIL_NOTE).toContain("Try again");
    expect(MORE_ANALYSIS).toBe("More analysis");
    expect(LESS_ANALYSIS).toBe("Hide analysis");
  });
});
