import { afterEach, describe, expect, it } from "vitest";
import {
  GOAL_ANALYSIS_KEY,
  readGoalAnalysis,
  writeGoalAnalysis,
} from "@/lib/control/goalAnalysisStore";
import { GOAL_BRIEF_ID_KEY } from "@/lib/control/goalProjectStore";
import { BLANK_DRAFT } from "@/components/control/GoalDraftFields";

describe("Goal analysis persist", () => {
  afterEach(() => {
    window.sessionStorage.removeItem(GOAL_ANALYSIS_KEY);
    window.localStorage.removeItem(GOAL_BRIEF_ID_KEY);
  });

  it("restores the brief with the drafts so Write still has a project id", () => {
    writeGoalAnalysis({
      project_id: "brief-1",
      project_title: "Saved looks",
      goal: "Shopper keeps Look A after refresh",
      acceptance: "Refresh shows Look A in Saved",
      analysis: {
        summary: "Persist the saved-looks draft across a refresh",
        split_reason: "single ticket, no split needed",
        code_inspected: false,
        code_limitation: "",
        fallback: false,
        tickets: [{ ...BLANK_DRAFT, selected: true, title: "Persist saved looks" }],
      },
    });
    const stored = readGoalAnalysis();
    expect(stored?.project_id).toBe("brief-1");
    expect(window.localStorage.getItem(GOAL_BRIEF_ID_KEY)).toBe("brief-1");
    expect(stored?.goal).toContain("Look A");
    expect(stored?.analysis.tickets[0]?.title).toBe("Persist saved looks");
    writeGoalAnalysis(null);
    expect(readGoalAnalysis()).toBeNull();
  });

  it("drops a session that has drafts but no brief", () => {
    window.sessionStorage.setItem(GOAL_ANALYSIS_KEY, JSON.stringify({
      goal: "Shopper keeps Look A after refresh",
      acceptance: "Refresh shows Look A in Saved",
      analysis: {
        tickets: [{ ...BLANK_DRAFT, selected: true, title: "Persist saved looks" }],
      },
    }));
    expect(readGoalAnalysis()).toBeNull();
  });
});
