import { describe, expect, it } from "vitest";
import { SIDEBAR_NAV, SIDEBAR_OFF_LIST, sidebarHrefs } from "@/lib/sidebar-nav";

describe("sidebar overlaps", () => {
  it("keeps exactly ten sidebar links and does not add pages", () => {
    expect(SIDEBAR_NAV).toHaveLength(10);
    expect(new Set(sidebarHrefs()).size).toBe(10);
  });

  it("keeps command-centre, /health, and /dashboard off the sidebar", () => {
    const hrefs = sidebarHrefs().join(" ");
    for (const path of SIDEBAR_OFF_LIST) {
      expect(hrefs).not.toContain(path);
    }
  });

  it("keeps Portfolio on /projects instead of a third health page", () => {
    expect(SIDEBAR_NAV.find((item) => item.key === "projects")?.href).toBe("/projects");
    expect(SIDEBAR_NAV.find((item) => item.key === "projects")?.label).toBe("Portfolio");
  });
});
