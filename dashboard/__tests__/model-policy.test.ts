import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EventEmitter } from "events";

const mocks = vi.hoisted(() => ({ execFileSync: vi.fn(), spawn: vi.fn() }));
vi.mock("child_process", () => ({ ...mocks, default: mocks }));

import { requireSubscriptionCLI, requireApiTransport } from "../lib/model-policy";
import { getAnalysisMode, makeClient, chatWithClaude, runPhase } from "../lib/claude";

beforeEach(() => {
  vi.clearAllMocks();
  for (const key of ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY", "ANALYSIS_MODE"]) vi.stubEnv(key, "");
  mocks.execFileSync.mockReturnValue(JSON.stringify({ loggedIn: true, authMethod: "claude.ai", subscriptionType: "max" }));
});
afterEach(() => vi.unstubAllEnvs());

describe("subscription-only model policy", () => {
  it("does not select metered analysis from an ambient API key", () => {
    vi.stubEnv("ANTHROPIC_API_KEY", "test-only");
    expect(getAnalysisMode()).toBe("cli");
    expect(makeClient()).toBeNull();
    expect(() => requireSubscriptionCLI()).toThrow(/subscription/i);
    expect(mocks.execFileSync).not.toHaveBeenCalled();
  });
  it("rejects paid transport before dispatch", () => {
    expect(() => requireApiTransport()).toThrow(/subscription/i);
    vi.stubEnv("ANALYSIS_MODE", "api");
    expect(() => makeClient()).toThrow(/subscription/i);
  });
  it("rejects a supplied SDK client without making a request", async () => {
    const client = { messages: { create: vi.fn() } };
    await expect(chatWithClaude(client as never, "test-model", [{ role: "user", content: "hello" }], "")).rejects.toThrow(/subscription/i);
    expect(client.messages.create).not.toHaveBeenCalled();
  });
  it.each(["{}", "not-json", JSON.stringify({ loggedIn: true, authMethod: "api_key", subscriptionType: "max" })])("blocks unverified CLI status %s", (status) => {
    mocks.execFileSync.mockReturnValue(status);
    expect(() => requireSubscriptionCLI()).toThrow(/subscription/i);
  });
  it("passes only shell and subscription settings to a verified CLI", () => {
    vi.stubEnv("GITHUB_TOKEN", "must-not-inherit");
    vi.stubEnv("SUPABASE_SERVICE_ROLE_KEY", "must-not-inherit");
    const env = requireSubscriptionCLI();
    expect(env.GITHUB_TOKEN).toBeUndefined();
    expect(env.SUPABASE_SERVICE_ROLE_KEY).toBeUndefined();
    expect(env.ANTHROPIC_API_KEY).toBeUndefined();
  });
  it("terminates analysis when its request is cancelled", async () => {
    const child = Object.assign(new EventEmitter(), {
      stdout: new EventEmitter(), stderr: new EventEmitter(), kill: vi.fn(),
    });
    mocks.spawn.mockReturnValue(child);
    const controller = new AbortController();
    const result = runPhase(null, "test-model", "prompt", "context", () => {}, controller.signal);
    controller.abort();
    await expect(result).rejects.toThrow(/aborted/i);
    expect(child.kill).toHaveBeenCalledWith("SIGTERM");
    expect(mocks.spawn.mock.calls[0][1]).toEqual(expect.arrayContaining(["--tools", "", "--strict-mcp-config"]));
  });
});
