/**
 * MC check 1 markers (e2e-live/real-data.ts): data-mc-data appears only on
 * output that came from the backend, never on loading, error or hard-coded
 * fallback output; data-mc-empty appears only on an honest empty state.
 * If a marker leaked onto a fallback, the live suite would pass a page that
 * loaded nothing. These cases pin the fallbacks found when the markers were added.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentRolesPanel from "@/components/control/AgentRolesPanel";
import CuratorProposalsPanel from "@/components/control/CuratorProposalsPanel";
import HealthGrid from "@/components/control/HealthGrid";
import SwarmPanel from "@/components/control/SwarmPanel";
import TerminalPanel from "@/components/control/TerminalPanel";

afterEach(() => {
  vi.unstubAllGlobals();
  cleanup();
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function stubFetch(route: (url: string) => Response): void {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => route(String(input))));
}

const marks = (attr: string): Element[] => Array.from(document.querySelectorAll(`[${attr}]`));

describe("check 1 markers", () => {
  it("curator: a named proposal is data; the '(unnamed)' fallback is not", async () => {
    stubFetch(() =>
      jsonResponse({
        total: 2,
        returned: 2,
        by_status: { pending: 2 },
        proposals: [
          { proposal_id: "p1", ts: new Date().toISOString(), status: "pending", proposed_skill_name: "retry-flaky-ci" },
          { proposal_id: "p2", ts: new Date().toISOString(), status: "pending" },
        ],
      }),
    );
    render(<CuratorProposalsPanel />);
    await screen.findByText("(unnamed)");
    expect(marks("data-mc-data").map((m) => m.textContent)).toEqual(["retry-flaky-ci"]);
  });

  it("curator: empty list is an honest empty state; a failed read is neither", async () => {
    stubFetch(() => jsonResponse({ total: 0, returned: 0, proposals: [], by_status: {} }));
    render(<CuratorProposalsPanel />);
    await screen.findByText(/No pending proposals/);
    expect(marks("data-mc-empty")).toHaveLength(1);
    cleanup();

    stubFetch(() => jsonResponse({ error: "boom" }, 500));
    render(<CuratorProposalsPanel />);
    await screen.findByText(/boom/);
    expect(marks("data-mc-empty")).toHaveLength(0);
    expect(marks("data-mc-data")).toHaveLength(0);
  });

  it("swarm: the route's hard-coded UNKNOWN fallback carries no data mark", async () => {
    stubFetch((url) =>
      url.includes("kill-switch")
        ? jsonResponse({ killed: false })
        : jsonResponse({
            state: "UNKNOWN",
            autonomous_prs_today: null,
            autonomous_prs_limit: null,
            green_merges: null,
            green_merges_target: null,
            last_pr_ts: null,
            last_pr_url: null,
          }),
    );
    render(<SwarmPanel />);
    await screen.findByText("UNKNOWN");
    expect(marks("data-mc-data")).toHaveLength(0);
  });

  it("swarm: a real state and PR link are data", async () => {
    stubFetch((url) =>
      url.includes("kill-switch")
        ? jsonResponse({ killed: false })
        : jsonResponse({
            state: "ACTIVE",
            autonomous_prs_today: 2,
            autonomous_prs_limit: 5,
            green_merges: 1,
            green_merges_target: 3,
            last_pr_ts: new Date().toISOString(),
            last_pr_url: "https://github.com/CleanExpo/Pi-Dev-Ops/pull/1",
          }),
    );
    render(<SwarmPanel />);
    await screen.findByText("ACTIVE");
    await waitFor(() =>
      expect(marks("data-mc-data").map((m) => m.getAttribute("data-mc-data")).sort()).toEqual([
        "last-autonomous-pr",
        "swarm-state",
      ]),
    );
  });

  it("health grid: project tiles are data; an unreachable backend shows none", async () => {
    stubFetch(() =>
      jsonResponse([{ project_id: "pi-dev-ops", repo: "CleanExpo/Pi-Dev-Ops", overall_health: 88, scores: {}, findings_count: {}, deployments: {} }]),
    );
    render(<HealthGrid />);
    await screen.findByText("pi-dev-ops");
    expect(marks("data-mc-data")).toHaveLength(1);
    cleanup();

    stubFetch(() => jsonResponse({ detail: "down" }, 503));
    render(<HealthGrid />);
    await waitFor(() => expect(screen.queryByText(/unreachable|error|failed/i)).not.toBeNull());
    expect(marks("data-mc-data")).toHaveLength(0);
  });

  it("terminal: 'no tmux sessions' is honest empty only when the read succeeded", async () => {
    stubFetch((url) => (url.includes("sessions") ? jsonResponse({ sessions: [] }) : jsonResponse({ lines: [] })));
    render(<TerminalPanel />);
    await screen.findByText("No tmux sessions on this node.");
    expect(marks("data-mc-empty")).toHaveLength(1);
    cleanup();

    stubFetch(() => jsonResponse({ detail: "down" }, 503));
    render(<TerminalPanel />);
    await screen.findByText(/No sessions —/);
    expect(marks("data-mc-empty")).toHaveLength(0);
  });

  it("roles: live sessions stop counting once a refresh fails (rows stay on screen)", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let calls = 0;
    stubFetch(() => {
      calls += 1;
      return calls === 1
        ? jsonResponse([{ id: "s1", repo: "CleanExpo/Pi-Dev-Ops", status: "building", started: Date.now() / 1000 }])
        : jsonResponse({ detail: "down" }, 503);
    });
    render(<AgentRolesPanel />);
    await waitFor(() => expect(marks("data-mc-data")).toHaveLength(1));
    await vi.advanceTimersByTimeAsync(5_100);
    await screen.findByText(/retrying every 5s/);
    expect(marks("data-mc-data")).toHaveLength(0);
    vi.useRealTimers();
  });

  it("terminal: a host without tmux is an honest empty state, not an error", async () => {
    stubFetch(() => jsonResponse({ sessions: [], available: false, reason: "tmux is not installed on this host" }));
    render(<TerminalPanel />);
    await screen.findByText(/Not available on this host: tmux is not installed on this host/);
    expect(marks("data-mc-empty")).toHaveLength(1);
    expect(screen.queryByText(/No sessions —/)).toBeNull();
  });

  it("roles: nothing running is an honest empty state; a failed read is not", async () => {
    stubFetch(() => jsonResponse([]));
    render(<AgentRolesPanel />);
    await waitFor(() => expect(marks("data-mc-empty")).toHaveLength(1));
    expect(marks("data-mc-data")).toHaveLength(0);
    cleanup();

    stubFetch(() => jsonResponse({ detail: "down" }, 503));
    render(<AgentRolesPanel />);
    await screen.findByText(/retrying every 5s/);
    expect(marks("data-mc-empty")).toHaveLength(0);
  });
});
