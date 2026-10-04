/**
 * RA-7898 — a proxy 200 is live only when every row its panels read is
 * whole. One planted fault per test, from a complete payload.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { PROXY_FEEDS, readMissionControlLive } from "@/lib/boards/sources/feeds-proxy";
import { MC_LIVE, serve, signal, without } from "./boards-feed-fixtures";

afterEach(() => vi.unstubAllGlobals());

const read = (id: string) => PROXY_FEEDS.find((f) => f.id === id)!.read(signal);
const SESSION = { id: "s1", repo: "CleanExpo/RA", phase: "build", status: "running", elapsed_s: 30, issue_id: null };
const COMPLETION = { id: "c1", repo: "CleanExpo/RA", branch: null, score: 9, pr_url: null, issue_id: null, completed_at: null };
const PROJECT = { project_id: "RA", repo: "CleanExpo/RA", overall_health: 80, scores: { security: 80 }, findings_count: {}, deployments: {} };
const PIPELINE = { pipeline_id: "p", repo_url: "https://github.com/x/y", current_phase: "spec", phases_completed: [], updated_at: "2026-10-04T00:00:00Z" };
const IDEA = { snapshot: { intake: "", north_star: "", awaiting: 0, packet: null, verdicts: [], go_required: true, executed: false } };

describe("mission-control/live rows", () => {
  it("complete rows are live", async () => {
    serve({ ...MC_LIVE, active_sessions: [SESSION], recent_completions: [COMPLETION] });
    expect((await readMissionControlLive()).kind).toBe("live");
  });
  it("a null completion row is unreachable", async () => {
    serve({ ...MC_LIVE, recent_completions: [null] });
    expect((await readMissionControlLive()).kind).toBe("unreachable");
  });
  it.each([["session without id", { active_sessions: [without(SESSION, "id")] }],
    ["session with an object phase", { active_sessions: [{ ...SESSION, phase: {} }] }],
    ["completion with a text score", { recent_completions: [{ ...COMPLETION, score: "9" }] }],
    ["non-numeric hourly", { throughput: { hourly: ["1"] } }],
    ["queue with an object title", { queue: { urgent: 0, high: 0, next_issue_title: {} } }],
    ["pulse with a text count", { pulse: { comments_today: "2" } }],
    ["observability with a malformed action", { observability: { actions: [{ ok: "yes" }] } }],
  ])("%s is unreachable", async (_k, patch) => {
    serve({ ...MC_LIVE, ...patch });
    expect((await readMissionControlLive()).kind).toBe("unreachable");
  });
});

describe("projects/health rows", () => {
  it("a project with no scans yet (scores {}, health 100) is live", async () => {
    serve([{ ...PROJECT, overall_health: 100, scores: {} }]);
    expect((await read("projects-health")).kind).toBe("live");
  });
  it.each(["overall_health", "scores", "findings_count", "deployments"])("a row without %s is unreachable", async (key) => {
    serve([without(PROJECT, key)]);
    expect((await read("projects-health")).kind).toBe("unreachable");
  });
  it("an empty row is unreachable, never a live empty portfolio", async () => {
    serve([{}]);
    expect((await read("projects-health")).kind).toBe("unreachable");
  });
  it.each([["project_id", without(PROJECT, "project_id")], ["repo", without(PROJECT, "repo")],
    ["a text score", { ...PROJECT, scores: { security: "80" } }], ["a text health", { ...PROJECT, overall_health: "80" }],
  ])("a row missing or mistyping %s is unreachable", async (_k, row) => {
    serve([row]);
    expect((await read("projects-health")).kind).toBe("unreachable");
  });
});

describe("pipelines, idea-pipeline, sessions and health", () => {
  it("a complete pipeline row is live; each missing field is unreachable", async () => {
    serve([PIPELINE]);
    expect((await read("pipelines")).kind).toBe("live");
    for (const key of Object.keys(PIPELINE)) {
      serve([without(PIPELINE, key)]);
      expect((await read("pipelines")).kind, key).toBe("unreachable");
    }
  });
  it("a complete idea snapshot is live; each missing field is unreachable", async () => {
    serve(IDEA);
    expect((await read("idea-pipeline")).kind).toBe("live");
    for (const key of Object.keys(IDEA.snapshot)) {
      serve({ snapshot: without(IDEA.snapshot, key) });
      expect((await read("idea-pipeline")).kind, key).toBe("unreachable");
    }
  });
  it("a complete idea packet is live; empty decision records are unreachable", async () => {
    const packet = { idea_id: "i", text: "t", source: "s", status: "awaiting", verdict: null, recommended_verdict: "PROMOTE",
      go_at: null, executed: false, north_star_fit: { label: "fit", score: 4, rationale: "r" },
      effort_vs_impact: { effort: "S", impact: "H", rationale: "r" }, directive: { label: "d", rationale: "r" },
      displacement: { would_displace: "x", rationale: "r" }, judge: { score: null, decision: "go" },
      spm: { problem: "p", desired_outcome: "o", out_of_scope: "n" } };
    serve({ snapshot: { ...IDEA.snapshot, packet } });
    expect((await read("idea-pipeline")).kind).toBe("live");
    for (const [key, bad] of [["plan_packet_md", { message: "bad" }], ["linear_id", 7], ["source", undefined], ["execution_requested", "yes"]] as const) {
      serve({ snapshot: { ...IDEA.snapshot, packet: { ...packet, [key]: bad } } });
      expect((await read("idea-pipeline")).kind, key).toBe("unreachable");
    }
    for (const key of ["north_star_fit", "effort_vs_impact", "directive", "displacement", "judge", "spm"]) {
      serve({ snapshot: { ...IDEA.snapshot, packet: { ...packet, [key]: {} } } });
      expect((await read("idea-pipeline")).kind, key).toBe("unreachable");
    }
  });
  it("a session row the operator parser rejects is unreachable", async () => {
    serve([{ id: "s1" }]);
    expect((await read("sessions")).kind).toBe("unreachable");
  });
  it("health without a status is unreachable", async () => {
    serve({ uptime_s: 1 });
    expect((await read("pi-health")).kind).toBe("unreachable");
  });
});
