import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";
import { CONTROL_NAV, CONTROL_SECTIONS, isControlSectionSlug } from "../lib/control/nav";
import { controlTabActive, pathMatchesNav } from "../lib/nav-active";
import { proxy } from "../proxy";

describe("control sub-pages", () => {
  it("lists Goal → Linear as the first section", () => {
    expect(CONTROL_SECTIONS[0]?.slug).toBe("goal");
    expect(CONTROL_SECTIONS[0]?.href).toBe("/control/goal");
  });

  it("keeps section slugs unique and registered", () => {
    const slugs = CONTROL_SECTIONS.map((item) => item.slug);
    expect(new Set(slugs).size).toBe(slugs.length);
    for (const slug of slugs) {
      expect(isControlSectionSlug(slug)).toBe(true);
    }
  });

  it("includes Live plus every section in the subnav", () => {
    expect(CONTROL_NAV[0]?.href).toBe("/control");
    expect(CONTROL_NAV).toHaveLength(CONTROL_SECTIONS.length + 1);
  });
});

describe("nav active matching", () => {
  it("keeps Control highlighted on nested routes", () => {
    expect(pathMatchesNav("/control", "/control")).toBe(true);
    expect(pathMatchesNav("/control/goal", "/control")).toBe(true);
    expect(pathMatchesNav("/loop", "/control")).toBe(false);
  });

  it("marks Live only on the Control hub", () => {
    expect(controlTabActive("/control", "/control")).toBe(true);
    expect(controlTabActive("/control/goal", "/control")).toBe(false);
    expect(controlTabActive("/control/goal", "/control/goal")).toBe(true);
  });
});

describe("control sub-page auth", () => {
  it("redirects anonymous visitors away from /control/goal", async () => {
    const req = new NextRequest(new URL("https://pi.invalid/control/goal"));
    const res = await proxy(req);
    expect(res.status).toBeGreaterThanOrEqual(300);
    expect(res.status).toBeLessThan(400);
    expect(res.headers.get("location")).toContain("redirect=%2Fcontrol%2Fgoal");
  });
});
