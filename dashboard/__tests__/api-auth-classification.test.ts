/**
 * Is every API METHOD classified for auth — or did one quietly appear?
 *
 * WHY THE UNIT IS A METHOD, NOT A ROUTE.
 * The previous form of this control classified ROUTES. `/api/kill-switch` carried one entry
 * claiming `unauth_status: 401`, and its own reason line acknowledged that `GET ?op=status`
 * is called unauthenticated by design. Both statements were recorded and neither was wrong
 * in isolation: POST refuses at 401, GET answers 200. A single per-route number cannot be
 * true of both, so the entry was structurally incapable of being correct, and no assertion
 * compared the declared number to reality.
 *
 * The same blindness produced the live defects found 2026-08-02: `/api/telegram` POST was
 * hardened to fail closed while its GET — which calls Telegram `setWebhook` with the live bot
 * token — was left open, and `/api/kill-switch` POST was hardened while its GET still reached
 * upstream with credentials. A route-level control cannot see either, because in both cases
 * the route is "classified" and one of its methods is not.
 *
 * PROXY GRANULARITY IS PATHS, SO PUBLIC PATHS NEED PER-METHOD ADJUDICATION.
 * proxy.ts is deny-by-default for /api: a path NOT on PUBLIC_API_ROUTES (lib/api-auth-policy.ts)
 * has every method gated, so it needs no entry. A public path has NO method gated — being public is not a
 * decision about any particular method, so each one still has to be adjudicated here. That is
 * why `/api/telegram` needs two entries despite being deliberately public: the webhook has to
 * be reachable, its registration endpoint does not.
 *
 * PROVENANCE IS REQUIRED, AND `discovery` FAILS.
 * Entries used to be written from observed posture and then read as declared requirement.
 * `/api/zte` and `/api/swarm-status` were never decided public; they fell through proxy.ts's
 * default-open fallthrough and were documented afterwards as "deliberately-public". Every
 * entry now says whether it records a DECISION someone made or a DISCOVERY of what the code
 * already did, and a `discovery` is RED until somebody adjudicates it and signs it.
 *
 * NEVER resolve a red by writing down what the route currently does. That is the move that
 * produced the entries this rebuild exists to correct.
 */
import { describe, it, expect } from "vitest";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { PUBLIC_API_ROUTES, isApiPath, isPublicApiPath } from "../lib/api-auth-policy";

const ROOT = resolve(__dirname, "..");
const HTTP_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"] as const;


/**
 * Extract the HTTP methods a route file exports.
 *
 * Both export forms are matched. `export const GET = handle` is not a stylistic variant —
 * `/api/phone/gate` uses it, and a scan written only for `export async function` reported that
 * route as having no methods at all. A parser that silently returns nothing looks identical to
 * a route that is genuinely method-less, which is why emptiness is a failure below.
 */
function methodsOf(file: string): string[] {
  const src = readFileSync(file, "utf8");
  const alt = HTTP_METHODS.join("|");
  const found = new Set<string>();
  for (const re of [
    new RegExp(`export\\s+(?:async\\s+)?function\\s+(${alt})\\s*\\(`, "g"),
    new RegExp(`export\\s+const\\s+(${alt})\\s*[:=]`, "g"),
    new RegExp(`export\\s*\\{[^}]*?\\bas\\s+(${alt})\\b[^}]*?\\}`, "g"),
  ]) {
    for (const m of src.matchAll(re)) found.add(m[1]);
  }
  return [...found].sort();
}

interface Surface {
  key: string;      // "GET /api/kill-switch"
  path: string;
  method: string;
}

function discoverSurfaces(): { surfaces: Surface[]; methodless: string[] } {
  const surfaces: Surface[] = [];
  const methodless: string[] = [];
  (function walk(dir: string, urlPath: string) {
    if (!existsSync(dir)) return;
    for (const e of readdirSync(dir)) {
      const p = join(dir, e);
      if (statSync(p).isDirectory()) {
        walk(p, e.startsWith("(") ? urlPath : `${urlPath}/${e}`);
      } else if (/^route\.(ts|tsx|js|jsx|mjs)$/.test(e)) {
        const ms = methodsOf(p);
        if (ms.length === 0) methodless.push(urlPath);
        for (const m of ms) surfaces.push({ key: `${m} ${urlPath}`, path: urlPath, method: m });
      }
    }
  })(join(ROOT, "app", "api"), "/api");
  return { surfaces: surfaces.sort((a, b) => a.key.localeCompare(b.key)), methodless };
}

type Entry = {
  classification: string;
  unauth_status: number;
  reason: string;
  provenance: "decision" | "discovery";
  decided_by: string;
  decided_on: string;
};

const DECLARED = JSON.parse(
  readFileSync(join(__dirname, "api-auth-classification.json"), "utf8"),
) as { surfaces: Record<string, Entry> };

const PUBLIC = Object.keys(PUBLIC_API_ROUTES);
const { surfaces: SURFACES, methodless: METHODLESS } = discoverSurfaces();

const isProxyProtected = (path: string) =>
  isApiPath(path) && !isPublicApiPath(path);

describe("api auth classification (method-aware)", () => {
  it("positive control: prefixes parsed, surfaces discovered, both export forms seen", () => {
    // Any of these empty makes every assertion below vacuous. The last two matter most: if
    // method extraction silently returned nothing, every surface would look classified because
    // there would be no surfaces at all.
    expect(PUBLIC.length, "PUBLIC_API_ROUTES is empty").toBeGreaterThan(0);
    expect(isProxyProtected("/api/pi-ceo/x"), "a non-public API path is not gated").toBe(true);
    expect(SURFACES.length, "discovered no method surfaces").toBeGreaterThan(10);

    // Prove the parser sees BOTH export forms, not just the common one. Pointing a working
    // instrument at the wrong target yields a confident null — see docs in the header.
    const fnForm = SURFACES.some((s) => s.path === "/api/kill-switch");
    const constForm = SURFACES.some((s) => s.path === "/api/phone/gate");
    expect(fnForm, "did not see `export async function` routes").toBe(true);
    expect(constForm, "did not see `export const GET = handle` routes (/api/phone/gate)").toBe(true);
  });

  it("no route file yields zero methods (a blind parser looks like a method-less route)", () => {
    expect(
      METHODLESS,
      "these route files exported no recognisable HTTP method. Either they genuinely export\n" +
        "none, or methodsOf() cannot see the form they use — and those two look identical from\n" +
        "here. Extend methodsOf() rather than ignoring them:\n" + METHODLESS.join("\n"),
    ).toEqual([]);
  });

  it("every method surface is classified — by the proxy, or explicitly with a reason", () => {
    const unclassified = SURFACES.filter(
      (s) => !isProxyProtected(s.path) && !DECLARED.surfaces[s.key],
    ).map((s) => s.key);
    expect(
      unclassified,
      "these METHOD surfaces are on PUBLIC_API_ROUTES (so the proxy gates none) and have no entry in\n" +
        "api-auth-classification.json, so nothing decides whether an anonymous caller may reach\n" +
        "them. A path being on PUBLIC_API_ROUTES does NOT classify its methods — the proxy\n" +
        "gates none of them, so each is adjudicated here. Classify each:\n" +
        unclassified.join("\n"),
    ).toEqual([]);
  });

  it("no declared entry describes a surface that no longer exists", () => {
    const live = new Set(SURFACES.map((s) => s.key));
    const phantom = Object.keys(DECLARED.surfaces).filter((k) => !live.has(k));
    expect(phantom, `declared surfaces with no handler on disk:\n${phantom.join("\n")}`).toEqual([]);
  });

  it("every declared entry carries reason, unauth_status, provenance and a signature", () => {
    const thin = Object.entries(DECLARED.surfaces)
      .filter(
        ([, v]) =>
          !v.reason?.trim() ||
          typeof v.unauth_status !== "number" ||
          !v.decided_by?.trim() ||
          !v.decided_on?.trim() ||
          (v.provenance !== "decision" && v.provenance !== "discovery"),
      )
      .map(([k]) => k);
    expect(thin, `incomplete entries:\n${thin.join("\n")}`).toEqual([]);
  });

  it("no entry is still an unadjudicated DISCOVERY", () => {
    // A discovery records what the code was found doing. Leaving one in place is how observed
    // posture becomes declared requirement without anyone choosing it.
    const undecided = Object.entries(DECLARED.surfaces)
      .filter(([, v]) => v.provenance === "discovery")
      .map(([k, v]) => `${k} (found doing this, never decided — ${v.reason.slice(0, 60)}…)`);
    expect(
      undecided,
      "these surfaces record what the code does, not a decision anyone made. Adjudicate each\n" +
        "and set provenance to `decision` with decided_by/decided_on. Do NOT resolve this by\n" +
        "writing down current behaviour:\n" + undecided.join("\n"),
    ).toEqual([]);
  });

  it("every classification is one the schema defines", () => {
    const known = Object.keys(
      (JSON.parse(readFileSync(join(__dirname, "api-auth-classification.json"), "utf8")) as
        { _classifications: Record<string, string> })._classifications,
    );
    const bogus = Object.entries(DECLARED.surfaces)
      .filter(([, v]) => !known.includes(v.classification))
      .map(([k, v]) => `${k}: ${v.classification}`);
    expect(bogus, `unknown classification (invent a label and it means nothing):\n${bogus.join("\n")}`).toEqual([]);
  });

  it("a pending-remediation entry names the change that closes it", () => {
    // Without this, the label degrades into a permanent excuse — which is what
    // "deliberately-public" had already become for the three surfaces it covered.
    const vague = Object.entries(DECLARED.surfaces)
      .filter(
        ([, v]) =>
          v.classification === "accepted-exposure-pending-remediation" &&
          !(v as Entry & { remediation?: string }).remediation?.trim(),
      )
      .map(([k]) => k);
    expect(vague, `accepted exposure with no named remediation:\n${vague.join("\n")}`).toEqual([]);
  });

  it("a 'route-self-protected' entry claims a refusing status, not a success", () => {
    const wrong = Object.entries(DECLARED.surfaces)
      .filter(([, v]) => v.classification === "route-self-protected" && v.unauth_status < 400)
      .map(([k, v]) => `${k}: claims self-protected but unauth_status=${v.unauth_status}`);
    expect(wrong, wrong.join("\n")).toEqual([]);
  });
});
