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
  "UGO_SUPABASE_URL",
  "UGO_SUPABASE_SERVICE_KEY",
  "NEXT_PUBLIC_SUPABASE_URL",
  "SUPABASE_SERVICE_ROLE_KEY",
] as const;

const saved: Record<string, string | undefined> = {};

beforeEach(() => {
  for (const k of ENV_KEYS) saved[k] = process.env[k];
  for (const k of ENV_KEYS) delete process.env[k];
});

afterEach(() => {
  for (const k of ENV_KEYS) {
    if (saved[k] === undefined) delete process.env[k];
    else process.env[k] = saved[k];
  }
});

describe("createUniteGroupServerClient", () => {
  it("throws a specific error when no Unite-Group service key is set", async () => {
    const { createUniteGroupServerClient } = await import("@/lib/supabase/unite-group-server");
    expect(() => createUniteGroupServerClient()).toThrowError(
      /SUPABASE_UNITE_GROUP_SERVICE_KEY/,
    );
  });

  it("does not fall back to the Pi-CEO client's env vars", async () => {
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

  it("constructs a client from the Railway UGO_* aliases", async () => {
    process.env.UGO_SUPABASE_URL = "https://lksfwktwtmyznckodsau.supabase.co";
    process.env.UGO_SUPABASE_SERVICE_KEY = "ugo-key";
    const { createUniteGroupServerClient } = await import("@/lib/supabase/unite-group-server");
    expect(() => createUniteGroupServerClient()).not.toThrow();
  });
});

/**
 * missingUniteGroupEnv() exists so the wiki-graph route can answer "was this
 * deployment ever configured?" WITHOUT catching an exception and parsing its
 * message. The URL has a public default, so only a missing key is reported.
 */
describe("missingUniteGroupEnv", () => {
  it("names the key when neither alias is set", async () => {
    const { missingUniteGroupEnv } = await import("@/lib/supabase/unite-group-server");
    expect(missingUniteGroupEnv()).toEqual(["SUPABASE_UNITE_GROUP_SERVICE_KEY"]);
  });

  it("is empty when the Railway alias supplies the key", async () => {
    process.env.UGO_SUPABASE_SERVICE_KEY = "ugo-key";
    const { missingUniteGroupEnv } = await import("@/lib/supabase/unite-group-server");
    expect(missingUniteGroupEnv()).toEqual([]);
  });

  it("returns nothing when both canonical vars are set (green control)", async () => {
    process.env.SUPABASE_UNITE_GROUP_URL = "https://lksfwktwtmyznckodsau.supabase.co";
    process.env.SUPABASE_UNITE_GROUP_SERVICE_KEY = "test-key";
    const { missingUniteGroupEnv } = await import("@/lib/supabase/unite-group-server");
    expect(missingUniteGroupEnv()).toEqual([]);
  });

  it("never returns a VALUE, only a name", async () => {
    const sentinel = ["VALUE", "MUST", "NOT", "APPEAR", "IN", "OUTPUT"].join("-");
    process.env.SUPABASE_UNITE_GROUP_URL = sentinel;
    const { missingUniteGroupEnv } = await import("@/lib/supabase/unite-group-server");
    const missing = missingUniteGroupEnv();
    expect(JSON.stringify(missing)).not.toContain(sentinel);
    expect(missing).toEqual(["SUPABASE_UNITE_GROUP_SERVICE_KEY"]);
  });

  it("keeps the thrown message in step with what it reports", async () => {
    const mod = await import("@/lib/supabase/unite-group-server");
    expect(() => mod.createUniteGroupServerClient()).toThrowError(
      /SUPABASE_UNITE_GROUP_SERVICE_KEY/,
    );
    expect(() => mod.createUniteGroupServerClient()).not.toThrowError(
      /SUPABASE_UNITE_GROUP_URL/,
    );
  });
});

describe("uniteGroupUrl", () => {
  it("defaults to the writer project's public URL", async () => {
    const { uniteGroupUrl, UNITE_GROUP_SUPABASE_URL } = await import(
      "@/lib/supabase/unite-group-server"
    );
    expect(uniteGroupUrl()).toBe(UNITE_GROUP_SUPABASE_URL);
    expect(UNITE_GROUP_SUPABASE_URL).toContain("lksfwktwtmyznckodsau");
  });
});
