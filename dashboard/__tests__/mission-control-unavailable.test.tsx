// Mission Control must show what is happening: a failed read is never a zero.
//
// The backend now reports a failed Linear queue or pulse read as
// `available: false` + `error` with null counts, and a failed session-store
// read as `null` (app/server/routes/mission_control.py, mission_control_sessions.py).
// The panel used to coerce every one of those to `0`, "No completions yet" or
// "Nothing authorized is running" — the same picture as a quiet, healthy system.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, within } from "@testing-library/react";
import LiveActivityFeed from "@/components/control/LiveActivityFeed";
import { isMissionControlLive } from "@/lib/boards/sources/validate-proxy";
import { activityEvents } from "@/lib/boards/views/shapes";

const OBS = { source: "health_full", ok: true, fully_observed: true, red_components: [], degraded_components: [], actions: [] };

function failedReads(overrides: Record<string, unknown> = {}) {
  return {
    ts: new Date().toISOString(),
    throughput: { hourly: null },
    active_sessions: null,
    recent_completions: null,
    queue: { available: false, error: "Linear rate limited", urgent: null, high: null, next_issue_id: null, next_issue_title: null },
    pulse: { available: false, error: "pulse issue not returned by Linear", last_at: null, comments_today: null, pulse_issue_id: null },
    observability: OBS,
    ...overrides,
  };
}

async function tile(label: string) {
  const el = await screen.findByText(label);
  return within(el.parentElement as HTMLElement);
}

function serve(payload: unknown) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(payload), { status: 200 })));
}

describe("Mission Control live feed — failed reads render UNAVAILABLE", () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    cleanup();
  });

  it("the feed validator accepts a payload that reports failed reads", () => {
    expect(isMissionControlLive(failedReads())).toBe(true);
  });

  it("queue: shows UNAVAILABLE and the reason, never 0 urgent", async () => {
    serve(failedReads());
    render(<LiveActivityFeed />);
    const queue = await tile("Linear queue");
    expect(queue.getByText("UNAVAILABLE")).toBeTruthy();
    expect(queue.getByText(/Linear rate limited/)).toBeTruthy();
    expect(queue.queryByText("0")).toBeNull();
  });

  it("pulse: shows UNAVAILABLE and the reason, never 0 comments today", async () => {
    serve(failedReads());
    render(<LiveActivityFeed />);
    const pulse = await tile("Pulse heartbeat");
    expect(pulse.getByText("UNAVAILABLE")).toBeTruthy();
    expect(pulse.getByText(/pulse issue not returned/)).toBeTruthy();
    expect(pulse.queryByText("0")).toBeNull();
  });

  it("throughput, sessions and completions: UNAVAILABLE, not empty", async () => {
    serve(failedReads());
    render(<LiveActivityFeed />);
    expect((await tile("24h throughput")).getByText("UNAVAILABLE")).toBeTruthy();
    expect(screen.queryByText(/No completions yet/)).toBeNull();
    expect(screen.queryByText(/Nothing authorized is running/)).toBeNull();
    expect(screen.getAllByText("UNAVAILABLE").length).toBeGreaterThanOrEqual(5);
  });

  it("an unreadable queue never lets idle sessions claim nothing is waiting", async () => {
    serve(failedReads({ active_sessions: [], recent_completions: [], throughput: { hourly: Array(24).fill(0) } }));
    render(<LiveActivityFeed />);
    await tile("Linear queue");
    expect(screen.queryByText(/Nothing authorized is running/)).toBeNull();
    expect(screen.getByText(/queue is unavailable/i)).toBeTruthy();
  });

  it("control: a real read of an empty system still shows measured zeros", async () => {
    serve(failedReads({
      throughput: { hourly: Array(24).fill(0) }, active_sessions: [], recent_completions: [],
      queue: { available: true, error: null, urgent: 0, high: 0, next_issue_id: null, next_issue_title: "" },
      pulse: { available: true, error: null, last_at: null, comments_today: 0, pulse_issue_id: "RA-1" },
    }));
    render(<LiveActivityFeed />);
    expect((await tile("Pulse heartbeat")).getByText("0")).toBeTruthy();
    expect(screen.queryByText("UNAVAILABLE")).toBeNull();
    expect(screen.getByText(/No completions yet/)).toBeTruthy();
    expect(screen.getByText("All companion signals observed.")).toBeTruthy();
  });

  it("observability with no actions list reported is unknown, never 'All companion signals observed.'", async () => {
    const { actions: _omit, ...withoutActions } = OBS;
    void _omit;
    serve(failedReads({ observability: withoutActions }));
    render(<LiveActivityFeed />);
    await screen.findByText(/Observability readiness/i);
    expect(screen.queryByText("All companion signals observed.")).toBeNull();
    expect(screen.getByText(/companion signals not reported/)).toBeTruthy();
  });
});

describe("boards activity view — null session lists are unknown, not empty", () => {
  it("returns null when the session store could not be read", () => {
    expect(activityEvents({ ts: "x", active_sessions: null, recent_completions: [] })).toBeNull();
    expect(activityEvents({ ts: "x", active_sessions: [], recent_completions: null })).toBeNull();
  });

  it("control: readable empty lists are an empty event list", () => {
    expect(activityEvents({ ts: "x", active_sessions: [], recent_completions: [] })).toEqual([]);
  });
});
