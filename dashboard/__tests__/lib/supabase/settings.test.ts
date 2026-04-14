/**
 * settings.test.ts — Unit tests for lib/supabase/settings.ts
 *
 * Tests getSettings() across all branches:
 * - Supabase not configured (createServerClient throws) → falls back to DEFAULTS
 * - Supabase query returns an error → falls back to DEFAULTS
 * - Supabase returns rows → merges over env-var defaults
 * - cron_repos JSON parsing (valid and invalid)
 * - Unknown/unmapped keys in Supabase rows are ignored
 * - analysisModel env var default is correct
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Mock the Supabase server client before importing the module under test.
// vitest hoists vi.mock calls, so this is evaluated before any imports.
vi.mock("@/lib/supabase/server", () => ({
  createServerClient: vi.fn(),
}));

import { createServerClient } from "@/lib/supabase/server";
const mockCreateServerClient = vi.mocked(createServerClient);

// Helper: build a chainable Supabase query mock that resolves to { data, error }
function mockSupabaseQuery(data: unknown[] | null, error: unknown = null) {
  const chain = {
    from: vi.fn().mockReturnThis(),
    select: vi.fn().mockResolvedValue({ data, error }),
  };
  mockCreateServerClient.mockReturnValue(chain as never);
  return chain;
}

describe("getSettings", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  // ── Fallback to DEFAULTS ────────────────────────────────────────────────

  it("returns env-var defaults when createServerClient throws", async () => {
    mockCreateServerClient.mockImplementation(() => { throw new Error("no config"); });
    vi.stubEnv("GITHUB_TOKEN", "gh-token-from-env");
    vi.stubEnv("ANALYSIS_MODEL", "claude-opus-4-6");

    const { getSettings } = await import("@/lib/supabase/settings");
    const s = await getSettings();

    expect(s.githubToken).toBe("gh-token-from-env");
    expect(s.analysisModel).toBe("claude-opus-4-6");
  });

  it("returns DEFAULTS when Supabase query returns an error", async () => {
    vi.stubEnv("ANTHROPIC_API_KEY", "sk-env-key");
    const chain = {
      from: vi.fn().mockReturnThis(),
      select: vi.fn().mockResolvedValue({ data: null, error: { message: "db error" } }),
    };
    mockCreateServerClient.mockReturnValue(chain as never);

    const { getSettings } = await import("@/lib/supabase/settings");
    const s = await getSettings();

    expect(s.anthropicApiKey).toBe("sk-env-key");
  });

  it("returns DEFAULTS when Supabase returns null data", async () => {
    mockSupabaseQuery(null);
    vi.stubEnv("WEBHOOK_SECRET", "sec-env");

    const { getSettings } = await import("@/lib/supabase/settings");
    const s = await getSettings();

    expect(s.webhookSecret).toBe("sec-env");
  });

  // ── Merging Supabase rows over defaults ─────────────────────────────────

  it("uses Supabase value over env-var default when row is present", async () => {
    mockSupabaseQuery([
      { key: "github_token", value: "gh-from-supabase" },
    ]);
    vi.stubEnv("GITHUB_TOKEN", "gh-from-env");

    const { getSettings } = await import("@/lib/supabase/settings");
    const s = await getSettings();

    expect(s.githubToken).toBe("gh-from-supabase");
  });

  it("maps all known Supabase keys to AppSettings fields", async () => {
    mockSupabaseQuery([
      { key: "github_token",       value: "gh" },
      { key: "anthropic_api_key",  value: "sk-ant" },
      { key: "analysis_model",     value: "claude-haiku-4-5" },
      { key: "webhook_secret",     value: "whsec" },
      { key: "vercel_token",       value: "vt" },
      { key: "telegram_bot_token", value: "tbt" },
      { key: "telegram_chat_id",   value: "123456" },
      { key: "linear_api_key",     value: "lin_api" },
    ]);

    const { getSettings } = await import("@/lib/supabase/settings");
    const s = await getSettings();

    expect(s.githubToken).toBe("gh");
    expect(s.anthropicApiKey).toBe("sk-ant");
    expect(s.analysisModel).toBe("claude-haiku-4-5");
    expect(s.webhookSecret).toBe("whsec");
    expect(s.vercelToken).toBe("vt");
    expect(s.telegramBotToken).toBe("tbt");
    expect(s.telegramChatId).toBe("123456");
    expect(s.linearApiKey).toBe("lin_api");
  });

  it("skips rows with empty value (keeps default)", async () => {
    mockSupabaseQuery([
      { key: "github_token", value: "" },
    ]);
    vi.stubEnv("GITHUB_TOKEN", "gh-from-env");

    const { getSettings } = await import("@/lib/supabase/settings");
    const s = await getSettings();

    expect(s.githubToken).toBe("gh-from-env");
  });

  it("ignores unknown / unmapped Supabase keys", async () => {
    mockSupabaseQuery([
      { key: "unknown_key_xyz", value: "should-be-ignored" },
    ]);

    const { getSettings } = await import("@/lib/supabase/settings");
    const s = await getSettings();

    // No key named 'unknown_key_xyz' on AppSettings — should not throw
    expect((s as unknown as Record<string, unknown>)["unknown_key_xyz"]).toBeUndefined();
  });

  // ── cron_repos JSON parsing ─────────────────────────────────────────────

  it("parses cron_repos as a JSON array", async () => {
    mockSupabaseQuery([
      { key: "cron_repos", value: '["repo-a","repo-b"]' },
    ]);

    const { getSettings } = await import("@/lib/supabase/settings");
    const s = await getSettings();

    expect(s.cronRepos).toEqual(["repo-a", "repo-b"]);
  });

  it("keeps cron_repos as empty array when JSON is malformed", async () => {
    mockSupabaseQuery([
      { key: "cron_repos", value: "not-valid-json" },
    ]);

    const { getSettings } = await import("@/lib/supabase/settings");
    const s = await getSettings();

    expect(s.cronRepos).toEqual([]);
  });

  // ── Default values ──────────────────────────────────────────────────────

  it("default analysisModel is claude-sonnet-4-6 when env var is undefined", async () => {
    // Don't stub ANALYSIS_MODEL — leave it undefined so the ?? fallback activates.
    // Stubbing to "" passes an empty string which .trim() returns as "", not the default.
    delete process.env.ANALYSIS_MODEL;
    mockSupabaseQuery([]);

    const { getSettings } = await import("@/lib/supabase/settings");
    const s = await getSettings();

    expect(s.analysisModel).toBe("claude-sonnet-4-6");
  });

  it("default cronRepos is an empty array", async () => {
    mockSupabaseQuery([]);

    const { getSettings } = await import("@/lib/supabase/settings");
    const s = await getSettings();

    expect(s.cronRepos).toEqual([]);
  });
});
