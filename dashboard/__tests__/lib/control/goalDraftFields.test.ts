import { describe, expect, it } from "vitest";
import { ALWAYS_SHOW, BLANK_DRAFT, fieldsForDraft, patchDraft } from "@/components/control/GoalDraftFields";

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

  it("shows goal, acceptance, and sub-tasks first", () => {
    expect(ALWAYS_SHOW).toEqual(["expected_behaviour", "acceptance", "sub_tasks"]);
    const ticket = {
      ...BLANK_DRAFT,
      selected: true,
      expected_behaviour: "Saved looks remain",
      acceptance: "Refresh keeps Look A",
      sub_tasks: "1. Persist the look",
      context: "Hidden until more",
    };
    expect(fieldsForDraft(ticket, false).map((field) => field.key)).toEqual(ALWAYS_SHOW);
    expect(fieldsForDraft(ticket, true).map((field) => field.key)).toContain("context");
    expect(fieldsForDraft(ticket, false).map((field) => field.label)).toEqual([
      "Goal",
      "Acceptance",
      "Sub-tasks",
    ]);
  });
});
