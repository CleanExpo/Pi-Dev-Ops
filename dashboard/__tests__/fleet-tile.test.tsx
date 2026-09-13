/**
 * UNI-2649 — Fleet tile renders enrolled machines, or "unavailable".
 * A fallback empty list must not look like a quiet fleet.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import FleetTile from "@/components/control/FleetTile";

afterEach(() => {
  vi.unstubAllGlobals();
  cleanup();
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("FleetTile", () => {
  it("shows each machine's revision, heartbeat, claim and checkedAt", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse({
          status: "ok",
          checkedAt: "2026-09-13T12:00:00.000Z",
          machines: [
            {
              host: "unite-mac-mini",
              revision: "mesh-runner@a1b2",
              lastHeartbeat: "2026-09-13T11:59:40.000Z",
              currentClaim: "UNI-2649",
              stale: false,
            },
          ],
        }),
      ),
    );
    render(<FleetTile />);
    expect(await screen.findByText("unite-mac-mini")).toBeTruthy();
    expect(screen.getByText(/revision mesh-runner@a1b2/)).toBeTruthy();
    expect(screen.getByText(/claim UNI-2649/)).toBeTruthy();
    expect(screen.getByText(/^checked /)).toBeTruthy();
    expect(screen.queryByText(/unavailable/i)).toBeNull();
  });

  it("renders unavailable when the BFF says so — not an empty fleet", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          { status: "unavailable", checkedAt: "2026-09-13T12:00:00.000Z", reason: "upstream unreachable" },
          503,
        ),
      ),
    );
    render(<FleetTile />);
    expect(await screen.findByText(/unavailable/i)).toBeTruthy();
    expect(screen.queryByText(/No machines enrolled/)).toBeNull();
  });

  it("renders unavailable when the fetch fails, not a placeholder fleet", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("network"); }));
    render(<FleetTile />);
    expect(await screen.findByText(/unavailable/i)).toBeTruthy();
    expect(screen.queryByText(/No machines enrolled/)).toBeNull();
  });

  it("CONTROL: a genuine empty enrolment is not labelled unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse({ status: "ok", checkedAt: "2026-09-13T12:00:00.000Z", machines: [] }),
      ),
    );
    render(<FleetTile />);
    expect(await screen.findByText(/No machines enrolled/)).toBeTruthy();
    expect(screen.queryByText(/unavailable/i)).toBeNull();
  });
});

describe("Loop Cockpit kill-switch row", () => {
  it("renders kill-switch state once /api/swarm/status answers", async () => {
    const { default: LoopCockpit } = await import("@/app/(main)/loop/page");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).includes("/api/swarm/status")) {
          return jsonResponse({
            swarm_enabled_env: true,
            kill_switch_active: true,
            escalation_lock_active: false,
            panic_count_last_hour: 1,
            pr_quota: { used: 1, limit: 3 },
          });
        }
        if (String(url).includes("/api/mesh-fleet")) {
          return jsonResponse({ status: "ok", checkedAt: "2026-09-13T12:00:00.000Z", machines: [] });
        }
        return jsonResponse({ enabled: true, stale: false, poller_iteration_errors: 0 });
      }),
    );
    render(<LoopCockpit />);
    await waitFor(() => expect(screen.getByText("ACTIVE")).toBeTruthy());
    expect(screen.getByLabelText("Swarm & Kill-Switch")).toBeTruthy();
  });
});
