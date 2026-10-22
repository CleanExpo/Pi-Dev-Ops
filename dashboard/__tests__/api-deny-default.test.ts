/**
 * Is every API route behind a session unless someone chose, in writing, to make it public?
 *
 * proxy.ts used to be ALLOW-by-default for /api: a route was public unless someone remembered
 * to add it to PROTECTED_API_PREFIXES. That reached main unprotected at least four times
 * (/command-centre, /api/attachments, /api/flow-board, /api/margot/bubble — the last one
 * attaching TAO_WEBHOOK_SECRET to a paid upstream call for any caller whose Cookie header
 * merely CONTAINED "tao_session=").
 *
 * It is now DENY-by-default. This file checks that behaviourally, against proxy() itself:
 *   - every route.ts on disk is DISCOVERED (never listed), probed anonymously, and must 401
 *     unless it is on PUBLIC_API_ROUTES with a written reason;
 *   - a path with no route at all must also 401 — that is what "by default" means;
 *   - every public entry names a route that exists, so the list cannot rot into a wildcard.
 */
import { describe, it, expect } from "vitest";
import { NextRequest } from "next/server";
import { existsSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { unstable_doesMiddlewareMatch } from "next/experimental/testing/server";
import { config, proxy } from "../proxy";
import { PUBLIC_API_ROUTES } from "../lib/api-auth-policy";

const ROOT = resolve(__dirname, "..");
const BASE = "https://pi.invalid";

async function outcome(path: string, method = "GET"): Promise<"401" | "through" | "other"> {
  const res = await proxy(new NextRequest(new URL(path, BASE), { method }));
  if (res.status === 401) return "401";
  // proxy() returns NextResponse.next() (status 200, x-middleware-next) when it lets a request on.
  if (res.headers.get("x-middleware-next") === "1") return "through";
  return "other";
}

/** Every route.ts under app/api as a probe-able URL. Dynamic segments get a sample value. */
function discoverRoutes(): string[] {
  const found: string[] = [];
  (function walk(dir: string, urlPath: string) {
    if (!existsSync(dir)) return;
    for (const e of readdirSync(dir)) {
      const p = join(dir, e);
      if (statSync(p).isDirectory()) {
        const seg = e.startsWith("(") ? "" : e.startsWith("[") ? "/sample" : `/${e}`;
        walk(p, `${urlPath}${seg}`);
      } else if (/^route\.(ts|tsx|js|jsx|mjs)$/.test(e)) {
        found.push(urlPath);
      }
    }
  })(join(ROOT, "app", "api"), "/api");
  return found.sort();
}

const ROUTES = discoverRoutes();
const PUBLIC = Object.keys(PUBLIC_API_ROUTES);

describe("proxy is deny-by-default for /api", () => {
  it("CONTROL: discovery found the route tree, including known protected and public routes", () => {
    expect(ROUTES.length, "discovered no API routes — every assertion below would be vacuous")
      .toBeGreaterThan(20);
    expect(ROUTES).toContain("/api/margot/bubble");
    expect(ROUTES).toContain("/api/auth/login");
    expect(ROUTES).toContain("/api/pi-ceo/sample");
  });

  it("CONTROL: a public route is let through, so a 401 below is a decision, not a broken probe", async () => {
    expect(await outcome("/api/revision")).toBe("through");
  });

  for (const route of ROUTES) {
    const isPublic = PUBLIC.includes(route);
    it(`${route} is ${isPublic ? "public by written decision" : "refused without a session"}`, async () => {
      if (isPublic) {
        expect(PUBLIC_API_ROUTES[route].trim().length, `${route} is public with no reason`)
          .toBeGreaterThan(20);
        expect(await outcome(route, "POST")).toBe("through");
      } else {
        for (const method of ["GET", "POST"]) {
          expect(
            await outcome(route, method),
            `${method} ${route} reached its handler with no session. Either it must require one ` +
              "(the default) or it belongs on PUBLIC_API_ROUTES in lib/api-auth-policy.ts with a reason.",
          ).toBe("401");
        }
      }
    });
  }

  it("a path with no route behind it is still refused (the default is deny)", async () => {
    expect(await outcome("/api/not-a-route-yet")).toBe("401");
    expect(await outcome("/api")).toBe("401");
  });

  it("near-miss spellings of a public route do not inherit its exemption", async () => {
    expect(await outcome("/api/revision-extra")).toBe("401");
    expect(await outcome("/api/revision/child")).toBe("401");
    expect(await outcome("/api/webhook/new-one")).toBe("401");
    expect(await outcome("/api/auth/logout-anything")).toBe("401");
  });

  it("case and percent-encoding variants of a protected route are not let through", async () => {
    expect(await outcome("/API/margot/bubble", "POST")).not.toBe("through");
    expect(await outcome("/%61pi/margot/bubble", "POST")).not.toBe("through");
    expect(await outcome("/api/margot/bubble/", "POST")).toBe("401");
  });

  // proxy() above is called directly, but Next only calls it for paths config.matcher selects.
  // The old matcher skipped anything ending in an image extension, so "/api/x%3F.png" never
  // reached the deny-by-default branch. Ask Next's own matcher.
  it("Next runs proxy for every /api route, whatever it ends in", () => {
    const variants = ROUTES.flatMap((r) => [r, `${r}.png`, `${r}%3F.svg`, `${r}/x.webp`]);
    variants.push("/api/pi-ceo/api/build%3F.png", "/api/pi-ceo/api/spec-pipeline/spec-x.png", "/api");
    const skipped = variants.filter(
      (url) => !unstable_doesMiddlewareMatch({ config, url: `${BASE}${url}` }),
    );
    expect(skipped, `/api paths proxy never sees:\n${skipped.join("\n")}`).toEqual([]);
  });

  it("CONTROL: the matcher still skips static assets, so the check above can fail", () => {
    expect(unstable_doesMiddlewareMatch({ config, url: `${BASE}/logo.png` })).toBe(false);
    expect(unstable_doesMiddlewareMatch({ config, url: `${BASE}/control` })).toBe(true);
  });

  it("every public entry names a route that exists on disk", () => {
    const phantom = PUBLIC.filter((p) => !ROUTES.includes(p));
    expect(phantom, `public entries with no route.ts behind them:\n${phantom.join("\n")}`).toEqual([]);
  });

  it("the public list is small and exact: no prefixes, no wildcards", () => {
    for (const p of PUBLIC) {
      expect(p, "public entries are exact /api paths").toMatch(/^\/api\/[a-z0-9\-/]+[a-z0-9]$/);
    }
    expect(PUBLIC.length).toBeLessThanOrEqual(10);
  });
});
