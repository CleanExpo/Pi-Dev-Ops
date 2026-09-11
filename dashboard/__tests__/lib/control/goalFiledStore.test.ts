import { afterEach, describe, expect, it } from "vitest";
import { GOAL_FILED_KEY, readGoalFiled, writeGoalFiled } from "@/lib/control/goalFiledStore";

const TICKET = {
  identifier: "RA-8001",
  url: "https://linear.app/unite-group/issue/RA-8001",
  title: "Saved looks persist",
  state: "Backlog",
  labels: ["pi-dev:source"],
};

describe("Goal filed persist", () => {
  afterEach(() => {
    window.sessionStorage.removeItem(GOAL_FILED_KEY);
  });

  it("keeps Linear links across a refresh", () => {
    writeGoalFiled([TICKET]);
    expect(readGoalFiled()).toEqual([TICKET]);
  });

  it("drops rows that have no identifier or url", () => {
    writeGoalFiled([{ ...TICKET, identifier: "", url: "" }]);
    expect(readGoalFiled()).toEqual([]);
  });
});
