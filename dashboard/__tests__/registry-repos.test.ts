import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { REGISTRY_REPOS, registryRepo } from "@/lib/control/registry-repos";

// The dashboard deploys from dashboard/, so it cannot read config/harness at run
// time. REGISTRY_REPOS mirrors the registry; this test fails on any drift.
describe("REGISTRY_REPOS", () => {
  it("equals the repos in config/harness/projects.json", () => {
    const file = path.resolve(__dirname, "../../config/harness/projects.json");
    const projects = JSON.parse(readFileSync(file, "utf8")).projects as Array<{ repo: string }>;
    expect([...REGISTRY_REPOS].sort()).toEqual([...new Set(projects.map((p) => p.repo))].sort());
  });
});

describe("registryRepo", () => {
  it("returns the registry spelling for a registered repo, ignoring case", () => {
    expect(registryRepo("cleanexpo/pi-dev-ops")).toBe("CleanExpo/Pi-Dev-Ops");
  });

  it.each([null, "", "evil/repo", "CleanExpo/Pi-Dev-Ops/../x", "CleanExpo/Pi-Dev-Ops?x=1", " CleanExpo/Pi-Dev-Ops"])(
    "refuses %j",
    (input) => expect(registryRepo(input)).toBeNull(),
  );
});
