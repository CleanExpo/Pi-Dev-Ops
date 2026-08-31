/**
 * createUniteGroupServerClient() is the fix for a real production bug: wiki_pages
 * lives in the Unite-Group prod Supabase project (lksfwktwtmyznckodsau), and the
 * wiki-graph route/page were reading through lib/supabase/server.ts's Pi-CEO-scoped
 * client instead (zbryrmxmgfmslqzizsto) — every read hit the wrong project's
 * PostgREST endpoint, got a 404, and surfaced as an opaque 500. This pins the one
 * property that matters: it fails loudly and specifically when its OWN env vars
 * are missing, rather than silently falling back to (or being confused with) the
 * Pi-CEO client's env vars.
 */
import { describe, it, expect, beforeEach, afterEach } from "vitest";

const ENV_KEYS = [
  "SUPABASE_UNITE_GROUP_URL",
  "SUPABASE_UNITE_GROUP_SERVICE_KEY",
  "NEXT_PUBLIC_SUPABASE_URL",
  "SUPABASE_SERVICE_ROLE_KEY",
] as const;

const saved: Record<string, string | undefined> = {};

beforeEach(() => {
  for (const k of ENV_KEYS) saved[k] = process.env[k];
});

afterEach(() => {
  for (const k of ENV_KEYS) {
    if (saved[k] === undefined) delete process.env[k];
    else process.env[k] = saved[k];
  }
});

describe("createUniteGroupServerClient", () => {
  it("throws a specific error when its own env vars are missing", async () => {
    delete process.env.SUPABASE_UNITE_GROUP_URL;
    delete process.env.SUPABASE_UNITE_GROUP_SERVICE_KEY;
    const { createUniteGroupServerClient } = await import("@/lib/supabase/unite-group-server");
    expect(() => createUniteGroupServerClient()).toThrowError(
      /SUPABASE_UNITE_GROUP_URL and SUPABASE_UNITE_GROUP_SERVICE_KEY/
    );
  });

  it("does not fall back to the Pi-CEO client's env vars", async () => {
    delete process.env.SUPABASE_UNITE_GROUP_URL;
    delete process.env.SUPABASE_UNITE_GROUP_SERVICE_KEY;
    process.env.NEXT_PUBLIC_SUPABASE_URL = "https://zbryrmxmgfmslqzizsto.supabase.co";
    process.env.SUPABASE_SERVICE_ROLE_KEY = "pi-ceo-key";
    const { createUniteGroupServerClient } = await import("@/lib/supabase/unite-group-server");
    expect(() => createUniteGroupServerClient()).toThrow();
  });

  it("constructs a client when its own env vars are present", async () => {
    process.env.SUPABASE_UNITE_GROUP_URL = "https://lksfwktwtmyznckodsau.supabase.co";
    process.env.SUPABASE_UNITE_GROUP_SERVICE_KEY = "test-key";
    const { createUniteGroupServerClient } = await import("@/lib/supabase/unite-group-server");
    expect(() => createUniteGroupServerClient()).not.toThrow();
  });
});

/**
 * missingUniteGroupEnv() exists so the wiki-graph route can answer "was this
 * deployment ever configured?" WITHOUT catching an exception and parsing its
 * message. That route's catch-all is deliberately message-free — a driver error
 * can carry a connection string — so before this, the one failure an operator can
 * act on looked exactly like the ones they cannot: a blank 500.
 *
 * Its return value goes straight into an HTTP response body, so the property that
 * has to hold is narrow and load-bearing: NAMES cross the boundary, values never
 * do.
 */
describe("missingUniteGroupEnv", () => {
  it("names both vars when neither is set", async () => {
    delete process.env.SUPABASE_UNITE_GROUP_URL;
    delete process.env.SUPABASE_UNITE_GROUP_SERVICE_KEY;
    const { missingUniteGroupEnv } = await import("@/lib/supabase/unite-group-server");
    expect(missingUniteGroupEnv()).toEqual([
      "SUPABASE_UNITE_GROUP_URL",
      "SUPABASE_UNITE_GROUP_SERVICE_KEY",
    ]);
  });

  it("names ONLY the var that is actually missing", async () => {
    // Precision, not just non-emptiness. An implementation that returned the
    // whole required list whenever anything was missing would satisfy the test
    // above and then tell an operator to set a variable they had already set.
    process.env.SUPABASE_UNITE_GROUP_URL = "https://lksfwktwtmyznckodsau.supabase.co";
    delete process.env.SUPABASE_UNITE_GROUP_SERVICE_KEY;
    const { missingUniteGroupEnv } = await import("@/lib/supabase/unite-group-server");
    expect(missingUniteGroupEnv()).toEqual(["SUPABASE_UNITE_GROUP_SERVICE_KEY"]);
  });

  it("returns nothing when both are set (green control)", async () => {
    // Without this, a function that always reported both missing would pass the
    // first test while permanently 503-ing a correctly configured deployment.
    process.env.SUPABASE_UNITE_GROUP_URL = "https://lksfwktwtmyznckodsau.supabase.co";
    process.env.SUPABASE_UNITE_GROUP_SERVICE_KEY = "test-key";
    const { missingUniteGroupEnv } = await import("@/lib/supabase/unite-group-server");
    expect(missingUniteGroupEnv()).toEqual([]);
  });

  it("never returns a VALUE, only a name", async () => {
    // The whole point is that this result is safe to serialise into a response.
    // The set variable here carries a secret-shaped value; it must not appear.
    const secret = "sb-service-role-DO-NOT-LEAK-0123456789";
    process.env.SUPABASE_UNITE_GROUP_URL = secret;
    delete process.env.SUPABASE_UNITE_GROUP_SERVICE_KEY;
    const { missingUniteGroupEnv } = await import("@/lib/supabase/unite-group-server");
    const missing = missingUniteGroupEnv();
    expect(JSON.stringify(missing)).not.toContain(secret);
    expect(missing).toEqual(["SUPABASE_UNITE_GROUP_SERVICE_KEY"]);
  });

  it("keeps the thrown message in step with what it reports", async () => {
    // The check and the error message read the same list, so they cannot drift
    // into disagreeing about which variable is missing.
    process.env.SUPABASE_UNITE_GROUP_URL = "https://lksfwktwtmyznckodsau.supabase.co";
    delete process.env.SUPABASE_UNITE_GROUP_SERVICE_KEY;
    const mod = await import("@/lib/supabase/unite-group-server");
    expect(() => mod.createUniteGroupServerClient()).toThrowError(
      /SUPABASE_UNITE_GROUP_SERVICE_KEY/
    );
    expect(() => mod.createUniteGroupServerClient()).not.toThrowError(
      /SUPABASE_UNITE_GROUP_URL/
    );
  });
});
