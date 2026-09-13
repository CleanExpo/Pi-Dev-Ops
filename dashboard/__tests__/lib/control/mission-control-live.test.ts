import { describe, expect, it } from "vitest";

import { completed24h } from "@/lib/control/mission-control-live";

describe("completed24h — UNI-2647 throughput.hourly", () => {
  it("sums the backend hourly buckets into a real number", () => {
    const hourly = Array.from({ length: 24 }, (_, i) => (i < 3 ? 2 : 0));
    expect(completed24h(hourly)).toBe(6);
  });

  it("is 0 when the hourly key is missing — not NaN, not undefined", () => {
    expect(completed24h(undefined)).toBe(0);
    expect(completed24h(null)).toBe(0);
    expect(completed24h([])).toBe(0);
  });

  it("does not invent a total from a different key name", () => {
    const payload = { hourly_24h: [1, 1, 1], hourly: [2, 0, 0] };
    expect(completed24h(payload.hourly)).toBe(2);
    expect(completed24h((payload as { hourly_24h?: number[] }).hourly_24h)).toBe(3);
  });
});
