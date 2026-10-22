// Loop Cockpit — a failed session-store or Linear read must render as
// unavailable, never as 0 or as an empty list.
//
// The backend sends `active_sessions: null`, `recent_completions: null`,
// `throughput.hourly: null` when the session store could not be read, and
// `queue: { available: false, error, urgent: null, high: null }` when Linear
// failed. The page used to coalesce every one of those to 0 / [] and print
// "No sessions running." at a store it never read (review P1, mc-truth-1).

import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup, waitFor } from "@testing-library/react";
import LoopCockpit from "@/app/(main)/loop/page";

const FAILED = {
  ts: new Date().toISOString(),
  throughput: { hourly: null },
  active_sessions: null,
  recent_completions: null,
  queue: { available: false, error: "Linear rate limited", urgent: null, high: null, next_issue_id: null },
  pulse: { available: false, error: "Linear rate limited", comments_today: null },
  observability: { fully_observed: false, degraded_components: [], actions: [] },
};

const GOOD = {
  ts: new Date().toISOString(),
  throughput: { hourly: Array.from({ length: 24 }, (_, i) => (i === 0 ? 4 : 0)) },
  active_sessions: [{ id: "s1", repo: "CleanExpo/Pi-Dev-Ops", phase: "building" }],
  recent_completions: [{ id: "c1", repo: "CleanExpo/CARSI" }],
  queue: { available: true, urgent: 3, high: 2, next_issue_id: null },
  pulse: { available: true, comments_today: 1 },
  observability: { fully_observed: true, degraded_components: [], actions: [] },
};

function mockLive(body: unknown) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => String(url).includes("/api/mission-control/live")
    ? new Response(JSON.stringify(body), { status: 200 })
    : new Response("nope", { status: 404 })));
}

/** Wait for the header clock to replace the loading marker: post-fetch state only. */
async function settle() {
  const synced = await screen.findByText(/^synced/);
  await waitFor(() => expect(synced.textContent).not.toMatch(/—/));
}

function valueText(label: string): string {
  return (screen.getByText(label).nextElementSibling as HTMLElement).textContent ?? "";
}

function rowText(label: string): string {
  return (screen.getByText(label).parentElement as HTMLElement).textContent ?? "";
}

describe("Loop Cockpit — failed reads", () => {
  afterEach(() => { vi.unstubAllGlobals(); cleanup(); });

  it("renders unavailable, never 0 or empty-state copy, when the reads failed", async () => {
    mockLive(FAILED);
    render(<LoopCockpit />);
    await settle();
    for (const label of ["Urgent queued", "High queued", "Completed (24h)", "Active sessions"]) {
      expect(valueText(label)).toMatch(/unavailable/i);
      expect(valueText(label)).not.toMatch(/\d/);
    }
    expect(screen.getAllByText(/Linear rate limited/).length).toBeGreaterThan(0);
    expect(screen.queryByText("No sessions running.")).toBeNull();
    expect(screen.queryByText("No completions yet.")).toBeNull();
    expect(screen.getByText(/running sessions are unknown/)).toBeTruthy();
    expect(screen.getByText(/recent completions are unknown/)).toBeTruthy();
  });

  it("positive control: a good payload still shows real counts and sessions", async () => {
    mockLive(GOOD);
    render(<LoopCockpit />);
    await settle();
    expect(rowText("Urgent queued")).toMatch(/Urgent queued\s*3/);
    expect(rowText("High queued")).toMatch(/High queued\s*2/);
    expect(rowText("Completed (24h)")).toMatch(/Completed \(24h\)\s*4/);
    expect(rowText("Active sessions")).toMatch(/Active sessions\s*1/);
    expect(screen.getByText("CleanExpo/Pi-Dev-Ops")).toBeTruthy();
    expect(screen.getByText("CleanExpo/CARSI")).toBeTruthy();
    for (const label of ["Urgent queued", "High queued", "Completed (24h)", "Active sessions"]) {
      expect(rowText(label)).not.toMatch(/unavailable/i);
    }
    expect(screen.queryByText(/Session store unavailable/i)).toBeNull();
  });
});
