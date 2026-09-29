/**
 * CeoHealthPanel (sidebar health light) — loaded, empty and error states (AAA check 7, MC-00).
 * Reads /health through fetchProxyJSON; null (backend unreachable) must read
 * "Backend unreachable", never a reachable service with blank rows.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const fetchProxyJSON = vi.fn<(path: string, init?: unknown) => Promise<unknown>>();

vi.mock("@/lib/pi-ceo-fetch", () => ({
  fetchProxyJSON: (path: string, init?: unknown) => fetchProxyJSON(path, init),
}));

import CeoHealthPanel from "@/components/CeoHealthPanel";

beforeEach(() => {
  fetchProxyJSON.mockReset();
});
afterEach(() => cleanup());

describe("CeoHealthPanel", () => {
  it("LOADED: a healthy backend is REACHABLE with uptime and the swarm state", async () => {
    fetchProxyJSON.mockResolvedValue({ status: "ok", uptime_s: 7260, swarm_enabled: false, swarm_shadow: true });
    render(<CeoHealthPanel />);
    expect(await screen.findByText("REACHABLE")).toBeTruthy();
    expect(screen.getByText("2h 1m")).toBeTruthy();
    expect(screen.getByText("Off")).toBeTruthy();
  });

  it("EMPTY: a bare health reply leaves the optional rows unknown, not invented", async () => {
    fetchProxyJSON.mockResolvedValue({ status: "ok" });
    render(<CeoHealthPanel />);
    expect(await screen.findByText("REACHABLE")).toBeTruthy();
    expect(screen.getByText("Unknown")).toBeTruthy();
    expect(screen.queryByText("Enabled")).toBeNull();
  });

  it("ERROR: backend unreachable (null) says so", async () => {
    fetchProxyJSON.mockResolvedValue(null);
    render(<CeoHealthPanel />);
    expect(await screen.findByText("Backend unreachable")).toBeTruthy();
    expect(screen.queryByText("REACHABLE")).toBeNull();
  });

  it("ERROR: a rejected read says the backend is unreachable", async () => {
    fetchProxyJSON.mockRejectedValue(new Error("aborted"));
    render(<CeoHealthPanel />);
    expect(await screen.findByText("Backend unreachable")).toBeTruthy();
  });
});
