/**
 * Is every API route classified for auth — or did one just quietly appear?
 *
 * `/api/kill-switch` was in NEITHER `PROTECTED_API_PREFIXES` nor `PUBLIC_API_PREFIXES`, so
 * `proxy()` never looked at it. Its POST could kill or resume the swarm with no credential,
 * while the route supplied `PI_CEO_PASSWORD` upstream itself. Nothing was broken — a route
 * had simply never been classified, and no check existed that could notice.
 *
 * A sweep of the other seven unclassified routes found no second instance: four self-protect
 * (smoke asserts 401) and three are deliberately public reads (smoke asserts 200). So the
 * value here is not the sweep, which is a snapshot. It is that an UNCLASSIFIED ROUTE NOW
 * FAILS, which is what makes the next one impossible to miss.
 *
 * Note the shape: the route SET is discovered from the filesystem, and the exceptions are
 * DECLARED with reasons. That is the declared-delta pattern from the provenance map, not a
 * fixed enumeration of the surface — the world can add a route, and when it does this goes
 * red until someone says what it is.
 */
import { describe, it, expect } from "vitest";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

const ROOT = resolve(__dirname, "..");

/** Parse the prefix arrays out of proxy.ts. Never retype them — a copy goes stale silently. */
function proxyPrefixes(name: string): string[] {
  const src = readFileSync(join(ROOT, "proxy.ts"), "utf8");
  const m = new RegExp(`${name}\\s*=\\s*\\[([^\\]]*)\\]`, "s").exec(src);
  if (!m) return [];
  return [...m[1].matchAll(/"([^"]+)"/g)].map((x) => x[1]);
}

function discoverApiRoutes(): string[] {
  const found: string[] = [];
  (function walk(dir: string, urlPath: string) {
    if (!existsSync(dir)) return;
    for (const e of readdirSync(dir)) {
      const p = join(dir, e);
      if (statSync(p).isDirectory()) {
        walk(p, e.startsWith("(") ? urlPath : `${urlPath}/${e}`);
      } else if (/^route\.(ts|tsx|js|jsx|mjs)$/.test(e)) {
        // Round-1 review: this matched only .ts/.tsx, so a future JS route shape would have
        // been invisible to the classification check — an unclassified route that the check
        // built to catch unclassified routes could not see.
        found.push(urlPath);
      }
    }
  })(join(ROOT, "app", "api"), "/api");
  return [...new Set(found)].sort();
}

const DECLARED = JSON.parse(
  readFileSync(join(__dirname, "api-auth-classification.json"), "utf8"),
) as {
  routes: Record<string, { classification: string; unauth_status: number; reason: string }>;
};

const PROTECTED = proxyPrefixes("PROTECTED_API_PREFIXES");
const PUBLIC = proxyPrefixes("PUBLIC_API_PREFIXES");
const ROUTES = discoverApiRoutes();

describe("api auth classification", () => {
  it("the prefix lists and the route list are both populated (positive control)", () => {
    // Any of these empty makes every assertion below vacuous: an empty PROTECTED list would
    // make routes look unclassified, and an empty route list would make the sweep pass over
    // nothing at all.
    expect(PROTECTED.length, "parsed no PROTECTED_API_PREFIXES from proxy.ts").toBeGreaterThan(0);
    expect(PUBLIC.length, "parsed no PUBLIC_API_PREFIXES from proxy.ts").toBeGreaterThan(0);
    expect(ROUTES.length, "discovered no API routes").toBeGreaterThan(5);
  });

  it("every API route is classified — by the proxy, or explicitly with a reason", () => {
    const unclassified = ROUTES.filter(
      (r) =>
        !PROTECTED.some((p) => r.startsWith(p)) &&
        !PUBLIC.some((p) => r.startsWith(p)) &&
        !DECLARED.routes[r],
    );
    expect(
      unclassified,
      "these API routes are in NEITHER proxy prefix list AND have no entry in\n" +
        "api-auth-classification.json, so nothing decides whether an anonymous caller may\n" +
        "reach them. That is exactly how /api/kill-switch POST became reachable with no\n" +
        "credential. Classify each one — protected, public, or declared with a reason:\n" +
        unclassified.join("\n"),
    ).toEqual([]);
  });

  it("no declared entry describes a route that no longer exists", () => {
    // A stale exception is a standing permission for a path nobody has looked at in months.
    const phantom = Object.keys(DECLARED.routes).filter((r) => !ROUTES.includes(r));
    expect(phantom, `declared classifications with no route on disk:\n${phantom.join("\n")}`).toEqual([]);
  });

  it("every declared entry carries a reason and an anonymous-caller status", () => {
    const thin = Object.entries(DECLARED.routes)
      .filter(([, v]) => !v.reason?.trim() || typeof v.unauth_status !== "number")
      .map(([k]) => k);
    expect(thin, `declared without a reason or unauth_status:\n${thin.join("\n")}`).toEqual([]);
  });

  it("a 'route-self-protected' entry claims a refusing status, not a success", () => {
    // The classification means "the route turns anonymous callers away". If the declared
    // status is a 2xx, the label and the claim disagree and the label is the lie.
    const wrong = Object.entries(DECLARED.routes)
      .filter(([, v]) => v.classification === "route-self-protected" && v.unauth_status < 400)
      .map(([k, v]) => `${k}: claims self-protected but unauth_status=${v.unauth_status}`);
    expect(wrong, wrong.join("\n")).toEqual([]);
  });
});
