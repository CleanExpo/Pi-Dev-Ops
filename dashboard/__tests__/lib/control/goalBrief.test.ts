import { describe, expect, it } from "vitest";
import {
  MIN_BRIEF,
  meetsMin,
  readyToAnalyze,
  readyToCreate,
  remainingHint,
} from "@/lib/control/goalBrief";

describe("Goal brief rules", () => {
  it("matches the server eight-character minimum", () => {
    expect(MIN_BRIEF).toBe(8);
    expect(meetsMin("1234567")).toBe(false);
    expect(meetsMin("12345678")).toBe(true);
    expect(meetsMin("  12345678")).toBe(true);
  });

  it("blocks Analyze until goal, acceptance, and a project are ready", () => {
    expect(readyToAnalyze("short", "acceptance long enough", "p1")).toBe(false);
    expect(readyToAnalyze("goal long enough", "short", "p1")).toBe(false);
    expect(readyToAnalyze("goal long enough", "acceptance long enough", "")).toBe(false);
    expect(readyToAnalyze("goal long enough", "acceptance long enough", "p1")).toBe(true);
  });

  it("blocks Save until title, description, and audience are ready", () => {
    expect(readyToCreate({ title: "short", description: "description long", audience: "audience long" })).toBe(false);
    expect(readyToCreate({
      title: "title long",
      description: "description long",
      audience: "audience long",
    })).toBe(true);
  });

  it("tells the operator how many characters remain", () => {
    expect(remainingHint("", "Goal")).toBe("Goal · required · 8+ characters");
    expect(remainingHint("abcd", "Goal")).toBe("Goal · 4 more characters");
    expect(remainingHint("abcdefgh", "Goal")).toBe("Goal · ready");
  });
});
