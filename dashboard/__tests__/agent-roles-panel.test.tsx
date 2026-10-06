/**
 * AgentRolesPanel — loaded, empty and error states (AAA check 7, MC-06).
 * Reads /api/sessions through fetchProxyJSON; null means the backend did not
 * answer, which must never read as "every role idle".
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const fetchProxyJSON = vi.fn<(path: string, init?: unknown) => Promise<unknown>>();

vi.mock("@/lib/pi-ceo-fetch", () => ({
  fetchProxyJSON: (path: string, init?: unknown) => fetchProxyJSON(path, init),
}));

import AgentRolesPanel from "@/components/control/AgentRolesPanel";

const now = () => Math.floor(Date.now() / 1000);

beforeEach(() => {
  fetchProxyJSON.mockReset();
});
afterEach(() => cleanup());

describe("AgentRolesPanel", () => {
  it("LOADED: an active session and a measured phase both render", async () => {
    fetchProxyJSON.mockResolvedValue([
      { id: "s1", repo: "https://github.com/CleanExpo/Pi-Dev-Ops", status: "building", started: now() - 30,
        last_phase: "plan", phase_metrics: { plan: { duration_s: 42, cost_usd: 0.0123, cost_basis: "reported_usage" } } },
    ]);
    render(<AgentRolesPanel />);
    expect(await screen.findByText("1 active")).toBeTruthy();
    expect(screen.getByText("CleanExpo/Pi-Dev-Ops")).toBeTruthy();
    expect(screen.getByText(/last: CleanExpo\/Pi-Dev-Ops · 42s · reported usage \$0\.0123/)).toBeTruthy();
    expect(fetchProxyJSON).toHaveBeenCalledWith("/api/sessions", { cache: "no-store" });
  });

  it("EMPTY: no sessions says idle, marks it honestly, and records no runs", async () => {
    fetchProxyJSON.mockResolvedValue([]);
    render(<AgentRolesPanel />);
    // "idle" also renders while loading, before data-mc-empty is set: wait for the loaded state.
    await waitFor(() =>
      expect(screen.getByText("idle").getAttribute("data-mc-empty")).toBe("no build session is running right now"));
    expect(screen.getAllByText("no runs recorded yet").length).toBe(6);
  });

  it("ERROR: backend unreachable (null) shows the error, not an idle fleet", async () => {
    fetchProxyJSON.mockResolvedValue(null);
    render(<AgentRolesPanel />);
    expect(await screen.findByText(/Pi-CEO backend unreachable/)).toBeTruthy();
    expect(document.querySelector("[data-mc-empty], [data-mc-data]")).toBeNull();
  });

  it("ERROR: a rejected read shows its message", async () => {
    fetchProxyJSON.mockRejectedValue(new Error("sessions exploded"));
    render(<AgentRolesPanel />);
    expect(await screen.findByText(/sessions exploded/)).toBeTruthy();
    expect(screen.queryByText("Loading…")).toBeNull();
  });
});
