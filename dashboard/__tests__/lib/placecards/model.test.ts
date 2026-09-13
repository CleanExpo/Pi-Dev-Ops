import { describe, expect, it } from "vitest";
import {
  applyAdvance,
  applyDecision,
  applySketchSave,
  canAdvance,
  remainingGates,
  seedCard,
} from "@/lib/placecards/model";

describe("placecards gates", () => {
  it("lets spark advance with an empty checklist", () => {
    const card = seedCard();
    expect(remainingGates(card)).toEqual([]);
    expect(canAdvance(card)).toBe(true);
  });

  it("blocks grill when only problem is empty", () => {
    const card = applyAdvance(seedCard());
    const blocked = {
      ...card,
      answers: {
        customer: "Restoration techs on site; the business owner pays.",
        metric: "80% of jobs have photos attached within 1 hour of arrival.",
        problem: "",
      },
    };
    expect(remainingGates(blocked)).toHaveLength(1);
    expect(remainingGates(blocked)[0]?.id).toBe("problem");
    expect(canAdvance(blocked)).toBe(false);
    expect(applyAdvance(blocked).moves).toHaveLength(1);
  });

  it("logs grill to shape exactly once after the problem is filled", () => {
    const grill = applyAdvance(seedCard());
    const ready = {
      ...grill,
      answers: {
        customer: "techs",
        metric: "photos in 1 hour",
        problem: "photos stay on phones",
      },
    };
    const shaped = applyAdvance(ready);
    expect(shaped.stage).toBe("shape");
    expect(shaped.moves.filter((row) => row.includes("grill → shape"))).toHaveLength(1);
  });

  it("saves one human excalidraw scene and does not duplicate it", () => {
    const once = applySketchSave(seedCard());
    const twice = applySketchSave(once);
    expect(twice.evidence).toEqual([{ kind: "excalidraw_scene", tag: "human" }]);
  });

  it("records a go without executing a second bet move", () => {
    const bet = { ...seedCard(), stage: "bet" as const, moves: ["spark → grill"] };
    const done = applyDecision(bet, true, "Clear pain, small bet.");
    expect(done.stage).toBe("graduated");
    expect(done.decision?.verdict).toBe("go");
    expect(done.moves.filter((row) => row.includes("bet → graduated"))).toHaveLength(1);
    expect(applyDecision(done, true, "again").moves.filter((row) => row.includes("bet → graduated"))).toHaveLength(1);
  });

  it("keeps the v1.1 bet gate as one combined item", () => {
    const bet = { ...seedCard(), stage: "bet" as const };
    expect(remainingGates(bet).map((gate) => gate.label)).toEqual([
      "goal card armed, promises logged",
    ]);
    expect(remainingGates({ ...bet, goalArmed: true, promises: ["keep photos"] })).toEqual([]);
  });
});
