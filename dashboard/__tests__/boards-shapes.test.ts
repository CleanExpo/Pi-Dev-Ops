/**
 * RA-7898 — shaping for the second views. Unknown stays unknown: an
 * unexpected payload is null (the view says so), never zeros.
 */
import { describe, expect, it } from "vitest";

import { buildRows, runningCount, stageOf } from "@/lib/boards/views/builds";
import {
  activityEvents, fabricLanes, fabricTotals, fleetRows, ideaFunnel, ideaInbox, pulse, scoredProjects, stationCounts,
} from "@/lib/boards/views/shapes";

describe("shapes return null for an unexpected payload", () => {
  it.each([
    ["fleetRows", () => fleetRows({ status: "unavailable", checkedAt: "x", reason: "r" })],
    ["activityEvents", () => activityEvents({ error: "boom" })],
    ["pulse", () => pulse({})],
    ["fabricTotals", () => fabricTotals({ enabled: false, healthy: false, error: "down" })],
    ["fabricLanes", () => fabricLanes(null)],
    ["scoredProjects", () => scoredProjects({ not: "a list" })],
    ["ideaFunnel", () => ideaFunnel(null)],
    ["ideaInbox", () => ideaInbox({} as never)],
    ["buildRows", () => buildRows([{ id: 1 }])],
  ])("%s", (_n, fn) => expect(fn()).toBeNull());
});

describe("scored projects", () => {
  it("a project with no scans has no score, never the scanner's default 100", () => {
    const rows = scoredProjects([
      { project_id: "A", repo: "a", overall_health: 100, scores: {} },
      { project_id: "B", repo: "b", overall_health: 61, scores: { security: 61 } },
    ]);
    expect(rows).toEqual([{ id: "B", repo: "b", score: 61 }, { id: "A", repo: "a", score: null }]);
  });
});

describe("builds", () => {
  it("maps statuses to stages and counts running", () => {
    expect(["queued", "running", "evaluating", "complete", "failed"].map(stageOf)).toEqual(["Queued", "Building", "Checking", "Done", "Stopped"]);
    const rows = buildRows([
      { id: "s1", repo: "r", status: "running", started: 1_700_000_000 },
      { id: "s2", repo: "r", status: "complete", started: 1_700_000_100 },
    ])!;
    expect(rows.map((r) => r.id)).toEqual(["s2", "s1"]);
    expect(runningCount(rows)).toBe(1);
  });
});

describe("ideas, stations, fabric, activity", () => {
  const packet = (id: string, verdict: string | null, go: string | null = null) => ({ idea_id: id, text: id, source: "telegram", verdict, go_at: go, executed: false });
  it("funnel and inbox come from the packets", () => {
    const payload = { snapshot: { awaiting: 1, packet: null }, packets: [packet("a", null), packet("b", "PROMOTE", "t"), packet("c", "PARK")] } as never;
    expect(ideaFunnel(payload)!.map((s) => s.count)).toEqual([3, 2, 1, 1, 0]);
    expect(ideaInbox(payload)).toEqual([{ id: "a", text: "a", source: "telegram" }]);
  });
  it("station counts by chip", () => {
    const s = (chip: "GREEN" | "RED" | "GREY") => ({ id: chip, name: chip, chip, reason: "" });
    expect(stationCounts([s("GREEN"), s("RED"), s("GREY"), s("GREY")])).toEqual({ green: 1, red: 1, grey: 2 });
  });
  it("fabric totals and lanes", () => {
    const status = { enabled: true, healthy: true, totals: { calls: 10, failures: 1 }, lanes: { review: { model: "m3", banned: false } } };
    expect(fabricTotals(status)!.map((b) => b.value)).toEqual([10, 1, 0, 0]);
    expect(fabricLanes(status)).toEqual([{ lane: "review", model: "m3", banned: false }]);
  });
  it("activity: completions and running sessions, newest first; pulse sums 24 hours", () => {
    const live = {
      active_sessions: [{ id: "x", repo: "R", phase: "build", elapsed_s: 10 }],
      recent_completions: [{ id: "y", repo: "S", completed_at: "2020-01-01T00:00:00Z", score: 9 }],
      throughput: { hourly: [1, 2, 3] },
    };
    expect(activityEvents(live)!.map((e) => e.key)).toEqual(["run-x", "done-y"]);
    expect(pulse(live)).toEqual({ total: 6, hourly: [1, 2, 3] });
  });
});
