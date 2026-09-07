import { afterEach, describe, expect, it } from "vitest";
import {
  GOAL_ANALYSIS_KEY,
  readGoalAnalysis,
  writeGoalAnalysis,
} from "@/lib/control/goalAnalysisStore";
import { BLANK_DRAFT } from "@/components/control/GoalDraftFields";

describe("Goal analysis persist", () => {
  afterEach(() => {
    window.sessionStorage.removeItem(GOAL_ANALYSIS_KEY);
  });

  it("restores drafts after a refresh and clears on discard", () => {
    writeGoalAnalysis({
      goal: "Shopper keeps Look A after refresh",
      acceptance: "Refresh shows Look A in Saved",
      analysis: {
        fallback: false,
        tickets: [{ ...BLANK_DRAFT, selected: true, title: "Persist saved looks" }],
      },
    });
    const stored = readGoalAnalysis();
    expect(stored?.goal).toContain("Look A");
    expect(stored?.analysis.tickets[0]?.title).toBe("Persist saved looks");
    writeGoalAnalysis(null);
    expect(readGoalAnalysis()).toBeNull();
  });
});
