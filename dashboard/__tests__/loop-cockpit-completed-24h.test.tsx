// Loop Cockpit — Completed (24h) must be the sum of throughput.hourly.
//
// UNI-2647: the page used to read a key the backend never sent. Existing
// cockpit tests mocked all-zero hourly arrays, so a broken mapping still
// rendered "0" and stayed green.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import LoopCockpit from "@/app/(main)/loop/page";

const HOURLY = Array.from({ length: 24 }, (_, i) => (i < 3 ? 2 : 0)); // 6

function mockLivePayload() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const body = String(url).includes("/api/mission-control/live")
        ? {
            ts: new Date().toISOString(),
            throughput: { hourly: HOURLY },
            active_sessions: [],
            recent_completions: [],
            queue: { urgent: 0, high: 0, next_issue_id: null },
            observability: { fully_observed: true, degraded_components: [], actions: [] },
          }
        : null;
      return body
        ? new Response(JSON.stringify(body), { status: 200 })
        : new Response("nope", { status: 404 });
    }),
  );
}

describe("Loop Cockpit — Completed (24h)", () => {
  beforeEach(mockLivePayload);
  afterEach(() => {
    vi.unstubAllGlobals();
    cleanup();
  });

  it("renders the sum of throughput.hourly as a real number", async () => {
    render(<LoopCockpit />);
    const label = await screen.findByText("Completed (24h)");
    const row = label.parentElement as HTMLElement;
    expect(row.textContent).toMatch(/Completed \(24h\)\s*6/);
    expect(row.textContent).not.toMatch(/undefined|NaN|\[object Object\]/);
  });
});
