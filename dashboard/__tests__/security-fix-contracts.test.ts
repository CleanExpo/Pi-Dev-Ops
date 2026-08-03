/**
 * Does any contract test still assert a behaviour a security fix removed?
 *
 * When a security defect is fixed, contract/smoke/snapshot tests that encoded the OLD
 * behaviour become assertions that the vulnerability is the requirement. They fail after the
 * fix, and they fail *pointing at the fix* — so the natural reading is that the hardening broke
 * something, and the natural remedy is to put the hole back.
 *
 * On 2026-08-02 this bit twice inside a single smoke entry: `expected_status: 200` for an
 * anonymous POST to /api/telegram, and `body_contains: ["ok"]`, which a 403 body never
 * satisfies. The second was caught only on a re-read. A human re-read is demonstrably not the
 * control, so this is the control.
 */
import { describe, it, expect } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";

const REPO = resolve(__dirname, "..", "..");
const REGISTRY = JSON.parse(
  readFileSync(join(__dirname, "security-fix-contract-registry.json"), "utf8"),
) as {
  fixes: Array<{
    id: string; path: string; method: string;
    pre_fix_status: number | null; post_fix_status: number;
    pre_fix_body_tokens: string[]; post_fix_body_tokens: string[]; reason: string;
  }>;
};

const SMOKE = join(REPO, ".github", "smoke-surfaces.json");

/** Every smoke surface entry, flattened. */
function smokeSurfaces(): Array<Record<string, unknown>> {
  if (!existsSync(SMOKE)) return [];
  const out: Array<Record<string, unknown>> = [];
  (function walk(o: unknown) {
    if (Array.isArray(o)) return o.forEach(walk);
    if (o && typeof o === "object") {
      const r = o as Record<string, unknown>;
      if (typeof r.path === "string" && typeof r.method === "string") out.push(r);
      Object.values(r).forEach(walk);
    }
  })(JSON.parse(readFileSync(SMOKE, "utf8")));
  return out;
}

describe("no contract asserts a behaviour a security fix removed", () => {
  const surfaces = smokeSurfaces();

  it("the registry and the smoke surfaces both loaded (positive control)", () => {
    expect(REGISTRY.fixes.length, "registry is empty").toBeGreaterThan(0);
    expect(surfaces.length, "no smoke surfaces parsed — the sweep would examine nothing")
      .toBeGreaterThan(10);
  });

  for (const fix of REGISTRY.fixes) {
    const matching = surfaces.filter(
      (s) => String(s.path).split("?")[0] === fix.path &&
             String(s.method).toUpperCase() === fix.method.toUpperCase(),
    );

    it(`[${fix.id}] no surface asserts the pre-fix STATUS`, () => {
      const bad = matching
        .filter((s) => fix.pre_fix_status !== null && s.expected_status === fix.pre_fix_status)
        .map((s) => `${s.name}: expected_status=${s.expected_status} (pre-fix) — ${fix.reason}`);
      expect(bad, bad.join("\n")).toEqual([]);
    });

    it(`[${fix.id}] no surface asserts a pre-fix BODY token`, () => {
      // The status is the obvious half. The body assertion is the half that was missed.
      const bad: string[] = [];
      for (const s of matching) {
        const tokens = Array.isArray(s.body_contains) ? (s.body_contains as string[]) : [];
        for (const t of tokens) {
          if (fix.pre_fix_body_tokens.includes(t) && !fix.post_fix_body_tokens.includes(t)) {
            bad.push(`${s.name}: body_contains "${t}" is pre-fix; a ${fix.post_fix_status} body never contains it`);
          }
        }
      }
      expect(bad, bad.join("\n")).toEqual([]);
    });

    it(`[${fix.id}] a surface that exists asserts the POST-fix status`, () => {
      // Without this, deleting the surface entirely would satisfy the checks above — the
      // vulnerability would stop being asserted by stopping being tested at all.
      if (matching.length === 0) return;
      const statuses = matching.map((s) => s.expected_status);
      expect(
        statuses,
        `a surface for ${fix.method} ${fix.path} exists but does not assert the post-fix ` +
          `status ${fix.post_fix_status}`,
      ).toContain(fix.post_fix_status);
    });
  }
});
