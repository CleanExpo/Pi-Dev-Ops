import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { phaseOutputs, malformedPhaseOutputs } from "./fixtures/phase-outputs";

const mocks = vi.hoisted(() => ({ runPhase: vi.fn(), pushFile: vi.fn(), createPR: vi.fn(), createBranch: vi.fn(), createDeployment: vi.fn(),
  persistence: { enabled: false, rejectCompletion: false, writes: [] as { table: string; action: string; payload: Record<string, unknown> }[] },
}));
vi.mock("@/lib/github", () => ({
  makeOctokit: () => ({ repos: { getContent: vi.fn().mockRejectedValue(new Error("missing optional context")) } }),
  parseRepoUrl: () => ({ owner: "org", repo: "project" }), getDefaultBranch: async () => "main",
  fetchRepoContext: async () => [], fetchBranchDiffs: async () => [], ...mocks,
}));
vi.mock("@/lib/claude", () => ({ makeClient: () => null, buildContext: () => "context", runPhase: mocks.runPhase, getAnalysisMode: () => "cli", THINK_SEEDS: {} }));
vi.mock("@/lib/supabase/settings", () => ({ getSettings: async () => ({ githubToken: "test-only", analysisModel: "test-model" }) }));
vi.mock("@/lib/supabase/server", () => ({ createServerClient: () => {
  if (!mocks.persistence.enabled) throw new Error("not configured");
  return { from: (table: string) => {
    const write = (action: string, payload: Record<string, unknown>) => {
      const query = {
        eq: () => query,
        then: (resolve: (value: { error: { message: string } | null }) => unknown) => {
          mocks.persistence.writes.push({ table, action, payload });
          return Promise.resolve(resolve({ error: mocks.persistence.rejectCompletion && table === "sessions" && payload.status === "done" ? { message: "receipt storage failed" } : null }));
        },
      };
      return query;
    };
    return { insert: (payload: Record<string, unknown>) => write("insert", payload), update: (payload: Record<string, unknown>) => write("update", payload) };
  } };
} }));
vi.mock("@/lib/vercel-api", () => ({ createDeployment: mocks.createDeployment, getProjectId: vi.fn() }));
import { GET } from "@/app/api/analyze/route";

const valid = JSON.stringify(phaseOutputs[1]);
const phaseFromPrompt = (prompt: string) => Number(prompt.match(/PHASE (\d)/)?.[1]);
const validPhase = (_client: unknown, _model: string, prompt: string) => Promise.resolve(JSON.stringify(phaseOutputs[phaseFromPrompt(prompt)]));
beforeEach(() => {
  vi.clearAllMocks(); mocks.runPhase.mockImplementation(validPhase); mocks.pushFile.mockResolvedValue(undefined);
  mocks.persistence.enabled = false; mocks.persistence.rejectCompletion = false; mocks.persistence.writes = [];
  mocks.createPR.mockResolvedValue("https://github.com/org/project/pull/1");
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("Unexpected external request")));
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });
const analyze = async () => (await GET(new NextRequest("http://localhost/api/analyze?repo=https://github.com/org/project"))).text();

describe("analysis delivery gate", () => {
  const invalidOutputs = [
    ...Object.keys(phaseOutputs).flatMap(id => [
      [Number(id), "empty object", {}], [Number(id), "array root", []], [Number(id), "string root", "invalid"],
    ] as [number, string, unknown][]),
    ...malformedPhaseOutputs.map(([id, reason, patch]) => [id, reason, { ...phaseOutputs[id], ...patch }] as [number, string, unknown]),
  ];
  it.each(invalidOutputs)("blocks phase %s %s before publication", async (phaseId, _reason, invalid) => {
    mocks.persistence.enabled = true;
    mocks.runPhase.mockImplementation((_client, _model, prompt: string) => Promise.resolve(JSON.stringify(
      phaseFromPrompt(prompt) === phaseId ? invalid : phaseOutputs[phaseFromPrompt(prompt)],
    )));
    const stream = await analyze();
    expect(stream).toContain("event: error");
    expect(stream).toContain(`Required phase ${phaseId} returned invalid output after retry`);
    expect(stream).not.toContain("event: done");
    expect(stream).not.toContain("=== ANALYSIS COMPLETE ===");
    expect(mocks.createBranch).not.toHaveBeenCalled();
    expect(mocks.pushFile).not.toHaveBeenCalled();
    expect(mocks.createPR).not.toHaveBeenCalled();
    expect(mocks.createDeployment).not.toHaveBeenCalled();
    expect(mocks.persistence.writes.some(write => write.table === "sessions" && write.payload.status === "done")).toBe(false);
  });
  it("dispatches configured PostgREST phase and completion writes", async () => {
    mocks.persistence.enabled = true;
    const stream = await analyze();
    expect(stream).toContain("event: done");
    expect(mocks.persistence.writes).toEqual(expect.arrayContaining([
      expect.objectContaining({ table: "phase_states", action: "update", payload: expect.objectContaining({ status: "done" }) }),
      expect.objectContaining({ table: "sessions", action: "update", payload: expect.objectContaining({ status: "done" }) }),
      expect.objectContaining({ table: "terminal_lines", action: "insert" }),
    ]));
  });
  it("makes a required completion receipt write failure visible instead of sending done", async () => {
    mocks.persistence.enabled = true; mocks.persistence.rejectCompletion = true;
    const stream = await analyze();
    expect(stream).toContain("event: error");
    expect(stream).not.toContain("event: done");
    expect(stream).not.toContain("=== ANALYSIS COMPLETE ===");
    expect(mocks.persistence.writes).toEqual(expect.arrayContaining([
      expect.objectContaining({ table: "sessions", payload: expect.objectContaining({ status: "error" }) }),
    ]));
  });
  it("does not publish any outputs or success when a required phase fails", async () => {
    mocks.persistence.enabled = true;
    mocks.runPhase.mockResolvedValueOnce(valid).mockRejectedValueOnce(new Error("required review unavailable"));
    const stream = await analyze();
    expect(stream).toContain("event: error");
    expect(stream).not.toContain("event: done");
    expect(mocks.pushFile).not.toHaveBeenCalled();
    expect(mocks.createPR).not.toHaveBeenCalled();
    expect(mocks.persistence.writes).toEqual(expect.arrayContaining([
      expect.objectContaining({ table: "phase_states", payload: expect.objectContaining({ status: "error" }) }),
      expect.objectContaining({ table: "sessions", payload: expect.objectContaining({ status: "error" }) }),
    ]));
  });
  it("blocks publication after a malformed phase and malformed retry", async () => {
    mocks.runPhase.mockResolvedValue("invalid");
    const stream = await analyze();
    expect(stream).not.toContain("event: done");
    expect(mocks.pushFile).not.toHaveBeenCalled();
    expect(mocks.createPR).not.toHaveBeenCalled();
  });
  it("does not report success when a harness file fails to publish", async () => {
    mocks.pushFile.mockImplementation(async (_o, _owner, _repo, _branch, name) => { if (name === ".harness/spec.md") throw new Error("push rejected"); });
    const stream = await analyze();
    expect(stream).toContain("event: error");
    expect(stream).not.toContain("event: done");
    expect(mocks.createPR).not.toHaveBeenCalled();
  });
  it("does not report completion when required pull request publication fails", async () => {
    mocks.createPR.mockRejectedValue(new Error("pull request rejected"));
    const stream = await analyze();
    expect(stream).toContain("event: error");
    expect(stream).not.toContain("event: done");
  });
  it("publishes successful analysis only after every required phase succeeds", async () => {
    const stream = await analyze();
    expect(stream).toContain("event: done");
    expect(mocks.runPhase).toHaveBeenCalledTimes(7);
    expect(mocks.createPR).toHaveBeenCalledTimes(1);
    expect(mocks.runPhase.mock.invocationCallOrder.at(-1)).toBeLessThan(mocks.pushFile.mock.invocationCallOrder[0]);
  });
  it("does not publish after the analysis budget expires", async () => {
    vi.useFakeTimers();
    mocks.runPhase.mockImplementation(async () => { await vi.advanceTimersByTimeAsync(270_001); throw new Error("aborted"); });
    const stream = await analyze();
    expect(stream).not.toContain("event: done");
    expect(mocks.pushFile).not.toHaveBeenCalled();
    expect(mocks.createPR).not.toHaveBeenCalled();
  });
});
