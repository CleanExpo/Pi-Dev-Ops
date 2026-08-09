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
