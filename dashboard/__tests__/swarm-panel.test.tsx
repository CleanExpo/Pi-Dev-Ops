/**
 * SwarmPanel — loaded, empty and error states (AAA check 7, MC-03).
 * Reads /api/swarm-status with fetch. The kill switch is its own panel with
 * its own tests (kill-switch-panel.test.tsx), so it is a stand-in here.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/control/KillSwitchPanel", () => ({
  default: () => <div data-testid="kill-switch" />,
}));

import SwarmPanel from "@/components/control/SwarmPanel";

function serve(body: unknown, status = 200) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status })));
}

const status = (over: Record<string, unknown>) => ({
  state: "OFF", autonomous_prs_today: 0, autonomous_prs_limit: 5,
  green_merges: null, green_merges_target: null, last_pr_ts: null, last_pr_url: null, ...over,
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("SwarmPanel", () => {
  it("LOADED: shows the state, today's PR count and a link to the last PR", async () => {
    serve(status({ state: "ACTIVE", autonomous_prs_today: 2, last_pr_ts: "2026-09-29T01:00:00Z",
      last_pr_url: "https://github.com/CleanExpo/Pi-Dev-Ops/pull/1" }));
    render(<SwarmPanel />);
    const badge = await screen.findByText("ACTIVE");
    expect(badge.closest("[data-mc-data]")?.getAttribute("data-mc-data")).toBe("swarm-state");
    expect(screen.getByText("2/5")).toBeTruthy();
    expect(screen.getByRole("link").getAttribute("href")).toBe("https://github.com/CleanExpo/Pi-Dev-Ops/pull/1");
    expect(screen.getByTestId("kill-switch")).toBeTruthy();
  });

  it("EMPTY: a stopped swarm with no PRs says OFF and 'Not observed', with no PR link", async () => {
    serve(status({}));
    render(<SwarmPanel />);
    expect(await screen.findByText("OFF")).toBeTruthy();
    expect(screen.getByText("0/5")).toBeTruthy();
    expect(screen.getByText("Not observed")).toBeTruthy();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("ERROR: a non-OK response shows the status and still mounts the kill switch", async () => {
    serve({ error: "down" }, 502);
    render(<SwarmPanel />);
    expect(await screen.findByText("HTTP 502")).toBeTruthy();
    expect(screen.getByTestId("kill-switch")).toBeTruthy();
    expect(document.querySelector("[data-mc-data]")).toBeNull();
  });

  it("ERROR: a rejected fetch shows its message", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("swarm offline"); }));
    render(<SwarmPanel />);
    expect(await screen.findByText("swarm offline")).toBeTruthy();
    expect(screen.queryByText("Loading…")).toBeNull();
  });
});
