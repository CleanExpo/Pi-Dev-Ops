/**
 * Does session verification have exactly ONE implementation?
 *
 * This is a STRUCTURAL claim, and structural claims are the ones that keep failing review.
 * Three have failed across this migration — "auth is enforced upstream by proxy.ts", "the vault
 * is not reached from here", "the verifier is shared with proxy.ts" — and every *behavioural*
 * claim that got tested held. Structural claims are the ones you believe because you wrote the
 * code, and that belief is what fails. So this one is a check that can go red, not a sentence
 * in a brief.
 *
 * `lib/auth-secret.ts` exists precisely because two callers once resolved the auth secret
 * differently: login succeeded while every protected page bounced. Verification now has
 * multiple callers too — `proxy.ts` and `/api/kill-switch` — so the same divergence is
 * available again, and "we'll consolidate it later" is how it stays available.
 *
 * WHAT THIS ASSERTS: every place that verifies a session token resolves to the single module
 * `lib/auth-secret.ts`. A second local implementation, anywhere, is a failure.
 *
 * IT IS EXPECTED TO BE RED ON `main` UNTIL THE CONSOLIDATION LANDS. The security hotfix
 * (PR #603) is deliberately additive and leaves `proxy.ts` with its own local verifier while
 * `auth-secret.ts` gains the shared one — two verifiers for a few days, chosen over leaving an
 * unauthenticated kill path live. This check is the tripwire on that trade: it turns green when
 * the consolidation arrives and stays red until it does.
 *
 * DO NOT exempt it, soften it, or add an allowance for the current state. A check written to
 * tolerate the thing it exists to catch is the exemption failure from the capability-2 round,
 * where an exemption keyed on file+rule quietly excused every future loss in that file.
 */
import { describe, it, expect } from "vitest";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

const ROOT = resolve(__dirname, "..");
const CANONICAL = "lib/auth-secret.ts";

/** Source files that could plausibly verify a session. Generated trees excluded. */
function sourceFiles(): string[] {
  const out: string[] = [];
  const SKIP = new Set([
    "node_modules", ".next", ".git", "coverage", "dist", "build", ".turbo", "__tests__",
  ]);
  (function walk(dir: string) {
    if (!existsSync(dir)) return;
    for (const e of readdirSync(dir)) {
      if (SKIP.has(e) || e.startsWith(".")) continue;
      const p = join(dir, e);
      if (statSync(p).isDirectory()) walk(p);
      else if (/\.(ts|tsx)$/.test(e)) out.push(p);
    }
  })(ROOT);
  return out;
}

const rel = (f: string) => f.slice(ROOT.length + 1).replace(/\\/g, "/");

/**
 * A local HMAC session verification, recognised by what it DOES rather than by name:
 * importing an HMAC primitive and comparing a computed digest against a token part.
 * Naming a function `verifySession` is optional; doing the work is not.
 */
function looksLikeLocalVerification(src: string): boolean {
  const hmac = /crypto\.subtle\.importKey|createHmac\s*\(/.test(src);
  const sessionish = /pi_session|issuedAt|SESSION_TTL|sessionToken/i.test(src);
  const compares = /===\s*sig|sig\s*===|expectedHex|timingSafeEqual/.test(src);
  return hmac && sessionish && compares;
}

describe("session verification has a single source of truth", () => {
  const files = sourceFiles().filter((f) => rel(f) !== CANONICAL);

  it("the file sweep is populated (positive control)", () => {
    // An empty sweep would make the assertion below pass while examining nothing.
    expect(files.length, "no source files were swept").toBeGreaterThan(10);
    expect(existsSync(join(ROOT, CANONICAL)), `${CANONICAL} is missing`).toBe(true);
  });

  it("the canonical module actually exports the verifier (positive control)", () => {
    // If this stopped exporting, "no local implementations" would be trivially satisfiable by
    // there being no verification anywhere — a green run over a broken system.
    const src = readFileSync(join(ROOT, CANONICAL), "utf8");
    expect(src).toMatch(/export\s+(async\s+)?function\s+verifySessionToken/);
  });

  it("no file outside the canonical module implements session verification itself", () => {
    const offenders = files
      .filter((f) => looksLikeLocalVerification(readFileSync(f, "utf8")))
      .map(rel);
    expect(
      offenders,
      "these files verify a session token themselves instead of importing it from\n" +
        `${CANONICAL}. Two implementations of the check that decides whether a request is\n` +
        "authenticated is the exact divergence that module was created to prevent — login\n" +
        "once succeeded while every protected page bounced, for this reason.\n" +
        "EXPECTED RED on main until PR #603's temporary duplication is consolidated.\n" +
        "Do not exempt this check; make it true.\n" +
        offenders.join("\n"),
    ).toEqual([]);
  });

  it("every consumer of session verification imports it from the canonical module", () => {
    const consumers = files.filter((f) => /verifySessionToken/.test(readFileSync(f, "utf8")));
    const notImporting = consumers.filter(
      (f) => !/from\s+["'](\.\/|@\/|\.\.\/)*lib\/auth-secret["']/.test(readFileSync(f, "utf8")),
    );
    expect(
      notImporting.map(rel),
      "these reference verifySessionToken without importing it from the canonical module",
    ).toEqual([]);
    // And there must be at least one consumer, or this proves nothing.
    expect(consumers.length, "nothing consumes verifySessionToken — is auth wired at all?")
      .toBeGreaterThan(0);
  });
});
