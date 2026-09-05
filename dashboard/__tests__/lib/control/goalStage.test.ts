import { describe, expect, it } from "vitest";
import { goalStage } from "@/lib/control/goalStage";

describe("Goal stage pills", () => {
  it("stays on Compose until Analyze starts", () => {
    expect(goalStage({ confirming: false, hasAnalysis: false, analyzing: false })).toBe(1);
  });

  it("marks Analyze while the model runs and after drafts return", () => {
    expect(goalStage({ confirming: false, hasAnalysis: false, analyzing: true })).toBe(2);
    expect(goalStage({ confirming: false, hasAnalysis: true, analyzing: false })).toBe(2);
  });

  it("marks Approve only when the operator is confirming a write", () => {
    expect(goalStage({ confirming: true, hasAnalysis: true, analyzing: false })).toBe(3);
  });
});
