import { describe, expect, it } from "vitest";
import {
  BRIEFS_EMPTY_NOTE,
  BRIEFS_LOAD_FAIL_NOTE,
  CHILD_TICKETS_NOTE,
  CONTROL_GOAL_CTA,
  CONTROL_HUB_LEDE,
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
  LINKS_STAY_NOTE,
  WRITE_MAYBE_STARTED,
  nextWriteHint,
  writeActionLabel,
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

  it("names Write the rest after a partial Linear write", () => {
    expect(writeActionLabel(2, true)).toBe("Write the rest (2)");
    expect(nextWriteHint([
      {
        title: "First ticket lands",
        goal: "goal long enough",
        acceptance: "Refresh shows Look A in Saved",
        selected: true,
        landed_identifier: "",
      },
      {
        title: "Already in Linear",
        goal: "goal long enough",
        acceptance: "Refresh shows Look A in Saved",
        selected: false,
        landed_identifier: "RA-8001",
      },
    ])).toContain("Write the rest");
    expect(LINKS_STAY_NOTE).toContain("Open each link");
    expect(WRITE_MAYBE_STARTED).toContain("Check Linear");
  });

  it("names the company loop after Write without starting work from Goal", () => {
    expect(CONTROL_HUB_LEDE).toContain("Ready for Pi-Dev");
    expect(CONTROL_HUB_LEDE).toContain("pi-dev:autonomous");
    expect(CONTROL_HUB_LEDE).toContain("watch Live");
    expect(LINKS_STAY_NOTE).toContain("does not start the build");
    expect(LINKS_STAY_NOTE).toContain("pi-dev:autonomous");
    expect(HOW_TO_GET_THE_GOAL.join(" ")).toContain("Ready for Pi-Dev");
  });
});
