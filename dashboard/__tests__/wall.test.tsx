/**
 * Wall — loaded, empty and error states (AAA check 7, MC-17).
 * Polls /api/mesh-fleet/wall. A failed or refused read keeps no snapshot, and
 * the wall must say its source is missing rather than show a quiet fleet.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams() }));

import { Wall } from "@/components/wall/Wall";

function serve(body: unknown, status = 200) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status })));
}

const snapshot = (fleet: Record<string, unknown>) => ({
  generated_at: new Date().toISOString(),
  banner: { red: 0, grey: 0 },
  fleet: { status: "ok", reason: "", machines: [], others: [], ...fleet },
  stations: [{ id: "capture", name: "Capture", chip: "GREEN", reason: "issue exists" }],
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Wall", () => {
  it("LOADED: a fresh snapshot shows each machine, its agents and the stations", async () => {
    serve(snapshot({ machines: [{ host: "Phills-Mac-mini", chip: "GREEN", reason: "fresh", ageSeconds: 5,
      load1: 0.4, selfReported: true, agents: [{ runtime: "claude", state: "idle", chip: "GREEN", ageSeconds: 5 }] }] }));
    render(<Wall />);
    expect(await screen.findByTestId("machine-Phills-Mac-mini")).toBeTruthy();
    expect(document.querySelector('[data-mc-data="fleet-heartbeat"]')).not.toBeNull();
    expect(screen.getByTestId("station-capture")).toBeTruthy();
    expect(screen.queryByTestId("wall-stale")).toBeNull();
  });

  it("EMPTY: a fleet with no live source says why and shows no machines", async () => {
    serve(snapshot({ status: "no_source", reason: "NO LIVE SOURCE YET — mesh secret not configured on the dashboard" }));
    render(<Wall />);
    expect((await screen.findByTestId("fleet-source")).textContent).toContain("NO LIVE SOURCE YET");
    expect(document.querySelector('[data-testid^="machine-"]')).toBeNull();
  });

  it("ERROR: a refused read keeps no snapshot and says the source is missing", async () => {
    // Snapshot-shaped on purpose: only the status code may reject it.
    serve(snapshot({}), 503);
    render(<Wall />);
    expect((await screen.findByTestId("wall-stale")).textContent).toContain("no timestamp");
    expect(screen.queryByTestId("station-capture")).toBeNull();
  });

  it("ERROR: a rejected fetch shows the stale banner, not an empty fleet", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("offline"); }));
    render(<Wall />);
    expect(await screen.findByTestId("wall-stale")).toBeTruthy();
    expect(screen.queryByTestId("fleet-source")).toBeNull();
  });
});
