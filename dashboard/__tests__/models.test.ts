/**
 * models.test.ts — Unit tests for lib/models.ts
 *
 * Verifies:
 * - MODELS constants have correct default values
 * - phaseModel() routes phases to worker vs analyst tiers correctly
 * - Model names are valid Claude 4.x series (not 3.5)
 * - Environment variable overrides work
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

describe("MODELS constants", () => {
  beforeEach(() => {
    // Clear module cache so env var changes take effect
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("WORKER default is claude-haiku-4-5 (not 3-5)", async () => {
    const { MODELS } = await import("@/lib/models");
    expect(MODELS.WORKER).toBe("claude-haiku-4-5");
  });

  it("ANALYST default is claude-sonnet-4-6", async () => {
    const { MODELS } = await import("@/lib/models");
    expect(MODELS.ANALYST).toBe("claude-sonnet-4-6");
  });

  it("ORCHESTRATOR default is claude-opus-4-6", async () => {
    const { MODELS } = await import("@/lib/models");
    expect(MODELS.ORCHESTRATOR).toBe("claude-opus-4-6");
  });

  it("DEFAULT matches ANALYST (sonnet-4-6)", async () => {
    const { MODELS } = await import("@/lib/models");
    expect(MODELS.DEFAULT).toBe(MODELS.ANALYST);
  });

  it("no model name contains '3-5' (regression: RA-889)", async () => {
    const { MODELS } = await import("@/lib/models");
    for (const [key, value] of Object.entries(MODELS)) {
      expect(value, `MODELS.${key} must not use 3-5 series`).not.toContain("3-5");
    }
  });

  it("all model names start with 'claude-'", async () => {
    const { MODELS } = await import("@/lib/models");
    for (const [key, value] of Object.entries(MODELS)) {
      expect(value, `MODELS.${key} must start with 'claude-'`).toMatch(/^claude-/);
    }
  });

  it("WORKER_MODEL env var overrides WORKER", async () => {
    vi.stubEnv("WORKER_MODEL", "claude-haiku-4-99");
    const { MODELS } = await import("@/lib/models");
    expect(MODELS.WORKER).toBe("claude-haiku-4-99");
  });

  it("ANALYST_MODEL env var overrides ANALYST", async () => {
    vi.stubEnv("ANALYST_MODEL", "claude-sonnet-4-99");
    const { MODELS } = await import("@/lib/models");
    expect(MODELS.ANALYST).toBe("claude-sonnet-4-99");
  });
});

describe("phaseModel()", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("phases 1, 2, 4 use WORKER (haiku — listing/summarisation)", async () => {
    const { phaseModel, MODELS } = await import("@/lib/models");
    expect(phaseModel(1)).toBe(MODELS.WORKER);
    expect(phaseModel(2)).toBe(MODELS.WORKER);
    expect(phaseModel(4)).toBe(MODELS.WORKER);
  });

  it("phases 3, 5, 6, 7 use the analyst model (sonnet — intelligence-heavy)", async () => {
    const { phaseModel, MODELS } = await import("@/lib/models");
    expect(phaseModel(3)).toBe(MODELS.ANALYST);
    expect(phaseModel(5)).toBe(MODELS.ANALYST);
    expect(phaseModel(6)).toBe(MODELS.ANALYST);
    expect(phaseModel(7)).toBe(MODELS.ANALYST);
  });

  it("phase 8 (commit/PR) uses analyst model", async () => {
    const { phaseModel, MODELS } = await import("@/lib/models");
    expect(phaseModel(8)).toBe(MODELS.ANALYST);
  });

  it("custom analyst model overrides non-worker phases", async () => {
    const { phaseModel } = await import("@/lib/models");
    expect(phaseModel(5, "claude-opus-4-6")).toBe("claude-opus-4-6");
    expect(phaseModel(7, "claude-opus-4-6")).toBe("claude-opus-4-6");
  });

  it("custom analyst model does NOT affect worker phases", async () => {
    const { phaseModel, MODELS } = await import("@/lib/models");
    // Worker phases always use MODELS.WORKER regardless of analyst override
    expect(phaseModel(1, "claude-opus-4-6")).toBe(MODELS.WORKER);
    expect(phaseModel(2, "claude-opus-4-6")).toBe(MODELS.WORKER);
    expect(phaseModel(4, "claude-opus-4-6")).toBe(MODELS.WORKER);
  });

  it("unknown phase defaults to analyst model", async () => {
    const { phaseModel, MODELS } = await import("@/lib/models");
    expect(phaseModel(99)).toBe(MODELS.ANALYST);
    expect(phaseModel(0)).toBe(MODELS.ANALYST);
  });
});
