/**
 * Does the proxy actually protect the command-centre?
 *
 * The wiki-graph port declares a delta against the `auth gate` rule. Its stated
 * reason is: "auth is enforced upstream by proxy.ts, whose matcher covers all
 * non-static routes and 401s without a session."
 *
 * That reason was asserted, never proven. It is the load-bearing claim under an
 * exemption the builder wrote to its own check, and the pages it exempts read
 * `wiki_pages` through a SERVICE-ROLE client that bypasses RLS. If the claim is
 * false, capability 2/3 ships an unauthenticated, RLS-bypassing read of the
 * knowledge base.
 *
 * The matcher does cover these paths — but matching is not enforcing. proxy()
 * only checks a session when the path hits PROTECTED_PAGE_PREFIXES or
 * PROTECTED_API_PREFIXES. This test exercises proxy() directly, with no cookie.
 *
 * POSITIVE CONTROL is mandatory here. "No redirect" is what a correctly-guarded
 * route and a completely broken test look like from the outside. `/control` is a
 * known-protected path: if the control does not redirect, this file proves
 * nothing and the assertions below are vacuous.
 */
import { describe, it, expect } from "vitest";
import { NextRequest } from "next/server";
import { proxy } from "../proxy";

const BASE = "https://pi.invalid";

/** A page/API request carrying NO session cookie. */
const anonymous = (path: string) => new NextRequest(new URL(path, BASE));

/** What did the proxy do — send them to login, refuse, or let them through? */
async function outcome(path: string): Promise<"redirect" | "401" | "through"> {
  const res = await proxy(anonymous(path));
  if (res.status === 401) return "401";
  // NextResponse.redirect() is a 307/308 with a location header.
  if (res.status >= 300 && res.status < 400 && res.headers.get("location")) return "redirect";
  return "through";
}

describe("proxy auth coverage", () => {
  // ---- POSITIVE CONTROL ----
  // Runs first and is asserted hardest. Every claim below is worthless if this
  // does not hold: it proves `outcome()` can actually observe enforcement.
  it("CONTROL: a known-protected page redirects an anonymous request", async () => {
    expect(
      await outcome("/control"),
      "positive control failed — /control is in PROTECTED_PAGE_PREFIXES and must redirect. " +
        "Until this passes, every other assertion in this file is vacuous.",
    ).toBe("redirect");
  });

  it("CONTROL: a known-protected API returns 401 to an anonymous request", async () => {
    expect(
      await outcome("/api/pi-ceo/api/health"),
      "positive control failed — /api/pi-ceo is in PROTECTED_API_PREFIXES and must 401.",
    ).toBe("401");
  });

  // ---- THE CLAIM UNDER TEST ----
  // Every command-centre surface, including the two the delta exempts.
  const PAGES = [
    "/command-centre",
    "/command-centre/hermes",
    "/command-centre/knowledge",
    "/command-centre/wiki-graph",
  ];

  for (const path of PAGES) {
    it(`${path} is not reachable without a session`, async () => {
      expect(
        await outcome(path),
        `${path} rendered for an anonymous request. The wiki-graph 'auth gate' delta ` +
          `states auth is enforced upstream by proxy.ts — this is that claim, checked.`,
      ).toBe("redirect");
    });
  }

  it("/api/command-centre/wiki-graph 401s without a session", async () => {
    expect(
      await outcome("/api/command-centre/wiki-graph"),
      "the wiki-graph API served an anonymous request. It reads wiki_pages through a " +
        "service-role client that bypasses RLS, so this is an unauthenticated read of the " +
        "whole knowledge base.",
    ).toBe("401");
  });
});
