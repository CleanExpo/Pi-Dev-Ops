import { describe, expect, it } from "vitest";
import { isPhaseOutputValid } from "@/lib/phase-output";
import { phaseOutputs, malformedPhaseOutputs } from "./fixtures/phase-outputs";

describe("required analysis phase contracts", () => {
  it.each(Object.keys(phaseOutputs).map(Number))("accepts the phase %s contract including legitimate empty lists", id => {
    expect(isPhaseOutputValid(id, JSON.stringify(phaseOutputs[id]))).toBe(true);
  });
  it.each(Object.entries(phaseOutputs).flatMap(([id, fields]) => Object.keys(fields).map(key => [Number(id), key] as const)))(
    "rejects phase %s with required field %s omitted", (id, key) => {
      const partial = { ...phaseOutputs[id] };
      delete partial[key];
      expect(isPhaseOutputValid(id, JSON.stringify(partial))).toBe(false);
    },
  );
  it.each(malformedPhaseOutputs)("rejects phase %s %s", (id, _reason, patch) => {
    expect(isPhaseOutputValid(id, JSON.stringify({ ...phaseOutputs[id], ...patch }))).toBe(false);
  });
  it("accepts fully populated nested contracts", () => {
    const values = {
      2: { components: [{ name: "math", responsibility: "Calculate", file: "math.ts" }] },
      3: { issues: [{ severity: "low", file: "math.ts", line: null, description: "Missing docs" }] },
      6: { sprints: [{ id: 1, name: "Docs", duration: "1d", goal: "Explain API", items: [{ title: "Write docs", size: "S", priority: "P2", piter: { problem: "Missing docs", impact: "Hard to use", result: "Documented API" } }] }],
        featureList: [{ id: "F001", title: "Write docs", sprint: 1, status: "planned" }] },
      7: { nextActions: [{ action: "Review docs", why: "Usability", effort: "S", owner: "human" }] },
    };
    for (const [id, patch] of Object.entries(values)) {
      expect(isPhaseOutputValid(Number(id), JSON.stringify({ ...phaseOutputs[Number(id)], ...patch }))).toBe(true);
    }
  });
  it("does not accept absent leverage dimensions or unsupported phase IDs", () => {
    expect(isPhaseOutputValid(5, JSON.stringify({ ...phaseOutputs[5], leveragePoints: [] }))).toBe(false);
    expect(isPhaseOutputValid(8, "{}")).toBe(false);
  });
});
