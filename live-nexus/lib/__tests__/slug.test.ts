import { describe, it, expect } from "vitest";
import { slugify } from "../slug";

describe("slugify", () => {
  it("converts plain title to slug", () => {
    expect(slugify("Acme Q2 Pricing")).toBe("acme-q2-pricing");
  });

  it("strips punctuation", () => {
    expect(slugify("Acme Q2 Pricing!?")).toBe("acme-q2-pricing");
  });

  it("collapses consecutive dashes", () => {
    expect(slugify("foo --- bar")).toBe("foo-bar");
  });

  it("trims leading/trailing dashes", () => {
    expect(slugify("—foo—")).toBe("foo");
  });

  it("ascii-folds unicode", () => {
    expect(slugify("Café Sync")).toBe("cafe-sync");
  });

  it("returns 'meeting' for empty input", () => {
    expect(slugify("")).toBe("meeting");
    expect(slugify("   ")).toBe("meeting");
  });

  it("caps length at 60 chars", () => {
    const result = slugify("a".repeat(200));
    expect(result.length).toBeLessThanOrEqual(60);
  });
});
