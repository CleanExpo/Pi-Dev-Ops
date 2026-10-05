import { describe, expect, it } from "vitest";
import { brisbaneDateTime, brisbaneTime } from "@/lib/brisbane-time";

// 2026-09-29T22:30:05Z is 08:30:05 on 30 Sept in Brisbane (UTC+10, no DST).
const UTC_LATE = "2026-09-29T22:30:05Z";

describe("brisbane-time", () => {
  it("shows Brisbane time, not the machine's zone", () => {
    expect(brisbaneTime(UTC_LATE)).toBe("08:30");
    expect(brisbaneTime(UTC_LATE, true)).toBe("08:30:05");
  });

  it("rolls the date over to Brisbane's day", () => {
    expect(brisbaneDateTime(UTC_LATE)).toMatch(/^30 Sep.*08:30$/);
  });

  it("stays UTC+10 in January (Brisbane has no daylight saving)", () => {
    expect(brisbaneTime("2026-01-15T00:00:00Z")).toBe("10:00");
  });
});
