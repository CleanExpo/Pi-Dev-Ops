/**
 * LiveActivityFeed — loaded, empty and error states (AAA check 7, MC-01).
 * mission-control-live-feed.test.tsx pins the throughput contract; this file
 * pins what the operator is told. A failed read must say so in the header,
 * never "live".
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const fetchProxyJSON = vi.fn<(path: string, init?: unknown) => Promise<unknown>>();

vi.mock("@/lib/pi-ceo-fetch", () => ({
  fetchProxyJSON: (path: string, init?: unknown) => fetchProxyJSON(path, init),
}));

import LiveActivityFeed from "@/components/control/LiveActivityFeed";

function payload(over: Record<string, unknown> = {}) {
  return {
    ts: new Date().toISOString(),
    throughput: { hourly: Array.from({ length: 24 }, (_, i) => (i < 3 ? 2 : 0)) },
    active_sessions: [],
    recent_completions: [],
    queue: { urgent: 0, high: 0, next_issue_id: null, next_issue_title: "" },
    pulse: { last_at: null, comments_today: 0, pulse_issue_id: null },
    ...over,
  };
}

beforeEach(() => {
  fetchProxyJSON.mockReset();
});
afterEach(() => cleanup());

describe("LiveActivityFeed", () => {
  it("LOADED: a clean read is live and shows the 24h total", async () => {
    fetchProxyJSON.mockResolvedValue(payload());
    render(<LiveActivityFeed />);
    expect(await screen.findByText("live · polling 5s")).toBeTruthy();
    const tile = within((await screen.findByText("24h throughput")).parentElement as HTMLElement);
    expect(tile.getByText("6")).toBeTruthy();
  });

  it("EMPTY: nothing running says so plainly", async () => {
    fetchProxyJSON.mockResolvedValue(payload());
    render(<LiveActivityFeed />);
    expect(await screen.findByText(/Nothing authorized is running/)).toBeTruthy();
  });

  it("ERROR: backend unreachable (null) is shown in the header, never live", async () => {
    fetchProxyJSON.mockResolvedValue(null);
    render(<LiveActivityFeed />);
    expect(await screen.findByText("⚠ Pi-CEO backend unreachable")).toBeTruthy();
    expect(screen.queryByText("live · polling 5s")).toBeNull();
  });

  it("ERROR: a payload carrying an error shows it and is not live", async () => {
    fetchProxyJSON.mockResolvedValue(payload({ error: "stale lease" }));
    render(<LiveActivityFeed />);
    expect(await screen.findByText("⚠ stale lease")).toBeTruthy();
    expect(screen.queryByText("live · polling 5s")).toBeNull();
    expect(screen.queryByText(/^updated /)).toBeNull();
  });
});
