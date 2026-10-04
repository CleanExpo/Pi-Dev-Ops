/**
 * RA-7898 — after a live read, a failed read must not leave the old numbers
 * or decision buttons on screen under the error. Live first, then failure.
 */
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import HealthGrid from "@/components/control/HealthGrid";
import IdeaPipelinePanel from "@/components/control/IdeaPipelinePanel";
import LiveActivityFeed from "@/components/control/LiveActivityFeed";
import { resetSources } from "@/lib/boards/sources";

afterEach(() => { cleanup(); resetSources(); vi.unstubAllGlobals(); vi.useRealTimers(); });

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

/** Serves `good` until `failing.on` is set, then a 503. */
function serveThenFail(good: unknown) {
  const failing = { on: false };
  vi.stubGlobal("fetch", vi.fn(async () => (failing.on ? json({}, 503) : json(good))));
  return failing;
}

describe("a failed read after a live one", () => {
  it("IdeaPipelinePanel drops the old count", async () => {
    vi.useFakeTimers();
    const failing = serveThenFail({ snapshot: { intake: "", north_star: "", awaiting: 3, packet: null, verdicts: [], go_required: true, executed: false } });
    render(<IdeaPipelinePanel />);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(screen.getByText("3 waiting for a decision")).toBeTruthy();
    failing.on = true;
    await act(async () => { await vi.advanceTimersByTimeAsync(60_001); });
    expect(screen.queryByText("3 waiting for a decision")).toBeNull();
    expect(screen.getByText("Board status unknown")).toBeTruthy();
  });

  it("LiveActivityFeed drops the old queue counts", async () => {
    vi.useFakeTimers();
    const failing = serveThenFail({ ts: new Date().toISOString(), throughput: { hourly: [] }, active_sessions: [],
      recent_completions: [], queue: { urgent: 7, high: 5 }, pulse: { last_at: null, comments_today: 0, pulse_issue_id: null } });
    render(<LiveActivityFeed />);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(screen.getByText("7")).toBeTruthy();
    failing.on = true;
    await act(async () => { await vi.advanceTimersByTimeAsync(5_001); });
    expect(screen.queryByText("7")).toBeNull();
    expect(screen.getAllByText(/unreachable/).length).toBeGreaterThan(0);
  });

  it("HealthGrid drops the old projects", async () => {
    vi.useFakeTimers();
    const failing = serveThenFail([{ project_id: "ra", repo: "CleanExpo/ra", overall_health: 88, scores: {}, findings_count: {}, deployments: {} }]);
    render(<HealthGrid />);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(screen.getByRole("button", { name: "ra health 88 out of 100" })).toBeTruthy();
    failing.on = true;
    await act(async () => { await vi.advanceTimersByTimeAsync(30_001); });
    expect(screen.queryByRole("button", { name: "ra health 88 out of 100" })).toBeNull();
  });

  it("HealthGrid shows an error, not a tile, for a partial project row", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json([{ project_id: "ra", repo: "CleanExpo/ra" }])));
    render(<HealthGrid />);
    expect(await screen.findByText(/invalid payload/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /ra health/ })).toBeNull();
  });
});
