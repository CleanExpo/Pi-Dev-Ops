/**
 * RA-7843 — a usage bar with no reading must not pose as a meter. ARIA requires
 * aria-valuenow on role="meter"; the live axe scan found five such bars on
 * /command-centre/providers (aria-required-attr, critical).
 */
import { describe, expect, it } from "vitest";

import { usageBarA11y } from "@/components/command-centre/provider-usage/ProviderUsageCockpit";

describe("usageBarA11y", () => {
  it("is a meter carrying its value when usage is known", () => {
    expect(usageBarA11y("Claude usage", 42)).toEqual({
      role: "meter",
      "aria-label": "Claude usage",
      "aria-valuenow": 42,
      "aria-valuemin": 0,
      "aria-valuemax": 100,
    });
  });

  it("keeps a real zero as a meter reading, not as unknown", () => {
    expect(usageBarA11y("Claude usage", 0)).toMatchObject({ role: "meter", "aria-valuenow": 0 });
  });

  it("says unknown, with no meter role, when there is no reading", () => {
    expect(usageBarA11y("Codex plan usage", null)).toEqual({
      role: "img",
      "aria-label": "Codex plan usage unknown",
    });
  });
});
