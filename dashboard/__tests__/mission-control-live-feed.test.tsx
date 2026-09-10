// Mission Control live feed — contract between the backend payload and the panel.
//
// Defect A: the backend sends `throughput.hourly` (app/server/routes/mission_control.py),
// the panel read `throughput.hourly_24h`, and the proxy's offline fallback emitted
// `hourly_24h` too. So the panel rendered when the backend was DOWN and threw
// `Math.max(...undefined)` when it was UP — the exact inverse of what a live panel
// should do. `dashboard/app/(main)/loop/page.tsx` already read `hourly`, which is
// what settles `hourly` as the contract.
//
// These tests are written to FAIL against the pre-fix component. Run them before
// the fix: test 1 and test 3 throw inside Sparkline.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, within } from "@testing-library/react";
import LiveActivityFeed from "@/components/control/LiveActivityFeed";

/** Exactly the shape app/server/routes/mission_control.py returns. */
function backendPayload(overrides: Record<string, unknown> = {}) {
  const hourly = Array.from({ length: 24 }, (_, i) => (i < 3 ? 2 : 0)); // 6 sessions
  return {
    ts: new Date().toISOString(),
    throughput: { hourly },
    active_sessions: [],
    recent_completions: [],
    queue: { urgent: 1, high: 2, next_issue_id: "RA-1", next_issue_title: "next up" },
    pulse: { last_at: null, comments_today: 0, pulse_issue_id: null },
    observability: {
      source: "health_full",
      ok: true,
      fully_observed: true,
      red_components: [],
      degraded_components: [],
      actions: [],
    },
    ...overrides,
  };
}

/** The throughput tile, so "0" here can never collide with a queue counter. */
async function throughputTile() {
  const label = await screen.findByText("24h throughput");
  return within(label.parentElement as HTMLElement);
}

function mockFetchOnce(payload: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(payload), { status: 200 })),
  );
}

describe("Mission Control live feed — throughput contract", () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    cleanup();
  });

  it("renders the 24h total from the backend's `hourly` key", async () => {
    mockFetchOnce(backendPayload());
    render(<LiveActivityFeed />);

    // 3 buckets x 2 = 6. Reading `hourly_24h` yields undefined and throws before
    // this ever renders.
    const tile = await throughputTile();
    expect(tile.getByText("6")).toBeTruthy();
    expect(tile.getByText(/sessions \/ 24h/)).toBeTruthy();
  });

  it("still renders the panel when the proxy fallback reports the backend down", async () => {
    // The offline fallback must speak the same contract as the backend.
    mockFetchOnce(
      backendPayload({
        throughput: { hourly: Array.from({ length: 24 }, () => 0) },
        observability: {
          source: "proxy_fallback",
          ok: false,
          fully_observed: false,
          red_components: ["pi_ceo_backend"],
          degraded_components: [],
          actions: [],
        },
      }),
    );
    render(<LiveActivityFeed />);
    expect(await screen.findByText("Mission Control")).toBeTruthy();
    expect((await throughputTile()).getByText("0")).toBeTruthy();
  });

  it("degrades instead of throwing when throughput is absent entirely", async () => {
    // A malformed or partial payload must not take the whole cockpit down.
    const { throughput, ...withoutThroughput } = backendPayload();
    void throughput;
    mockFetchOnce(withoutThroughput);

    render(<LiveActivityFeed />);
    expect(await screen.findByText("Mission Control")).toBeTruthy();
  });
});
