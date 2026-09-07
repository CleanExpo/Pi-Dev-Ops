import { describe, expect, it } from "vitest";
import { BLANK_DRAFT, patchDraft } from "@/components/control/GoalDraftFields";

describe("Goal draft patches", () => {
  it("clears sub_tasks_json when the operator edits the visible sub-tasks", () => {
    const ticket = {
      ...BLANK_DRAFT,
      selected: true,
      title: "Saved looks persist after refresh",
      goal: "Saved looks remain after refresh",
      acceptance: "Refresh keeps Look A in Saved",
      sub_tasks: "1. Original child",
      sub_tasks_json: '[{"title":"Original child"}]',
    };
    const next = patchDraft(ticket, { sub_tasks: "1. Persist saved looks after refresh" });
    expect(next.sub_tasks).toBe("1. Persist saved looks after refresh");
    expect(next.sub_tasks_json).toBe("");
  });
});
