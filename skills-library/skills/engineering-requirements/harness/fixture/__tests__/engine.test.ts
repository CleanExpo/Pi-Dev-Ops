import { describe, it, expect } from "vitest";
import { classify } from "../lib/engine";

describe("classify", () => {
  it("returns category 3 for sewage", () => {
    expect(classify({ source: "sewage" }).category).toBe(3);
  });
});
