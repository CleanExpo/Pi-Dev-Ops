import { afterEach, describe, expect, it } from "vitest";
import {
  GOAL_BRIEF_ID_KEY,
  readGoalBriefId,
  writeGoalBriefId,
} from "@/lib/control/goalProjectStore";

describe("Goal brief persist", () => {
  afterEach(() => {
    window.localStorage.removeItem(GOAL_BRIEF_ID_KEY);
  });

  it("round-trips a selected brief id", () => {
    writeGoalBriefId("brief-1");
    expect(readGoalBriefId()).toBe("brief-1");
    expect(window.localStorage.getItem(GOAL_BRIEF_ID_KEY)).toBe("brief-1");
  });

  it("clears an empty id so a refresh does not restore a blank project", () => {
    writeGoalBriefId("brief-1");
    writeGoalBriefId("   ");
    expect(readGoalBriefId()).toBe("");
    expect(window.localStorage.getItem(GOAL_BRIEF_ID_KEY)).toBeNull();
  });
});
