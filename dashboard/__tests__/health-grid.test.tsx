/**
 * HealthGrid — loaded, empty and error states of the project list (AAA check 7, MC-05).
 * Reads /api/projects/health through fetchProxyJSON; null means the backend
 * did not answer, which must never read as "no projects".
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const fetchProxyJSON = vi.fn<(path: string, init?: unknown) => Promise<unknown>>();

vi.mock("@/lib/pi-ceo-fetch", () => ({
  fetchProxyJSON: (path: string, init?: unknown) => fetchProxyJSON(path, init),
}));

import HealthGrid from "@/components/control/HealthGrid";

beforeEach(() => {
  fetchProxyJSON.mockReset();
});
afterEach(() => cleanup());

describe("HealthGrid", () => {
  it("LOADED: renders one tile per project with its score", async () => {
    fetchProxyJSON.mockResolvedValue([
      { project_id: "pi-dev-ops", repo: "CleanExpo/pi-dev-ops", overall_health: 88 },
      { project_id: "restoreassist", repo: "CleanExpo/restoreassist", overall_health: 41 },
    ]);
    render(<HealthGrid />);
    expect(await screen.findByRole("button", { name: "pi-dev-ops health 88 out of 100" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "restoreassist health 41 out of 100" })).toBeTruthy();
    // No cache option, as before the move; only the poller's abort signal.
    expect(fetchProxyJSON).toHaveBeenCalledWith("/api/projects/health", { signal: expect.any(AbortSignal) });
  });

  it("EMPTY: an empty list says no projects are registered", async () => {
    fetchProxyJSON.mockResolvedValue([]);
    render(<HealthGrid />);
    expect(await screen.findByText("No projects registered.")).toBeTruthy();
    expect(document.querySelector("[data-mc-data]")).toBeNull();
  });

  it("ERROR: backend unreachable (null) shows the error, not an empty list", async () => {
    fetchProxyJSON.mockResolvedValue(null);
    render(<HealthGrid />);
    expect(await screen.findByText("Pi-CEO backend unreachable")).toBeTruthy();
    expect(screen.queryByText("No projects registered.")).toBeNull();
  });

  it("ERROR: a rejected read shows its message", async () => {
    fetchProxyJSON.mockRejectedValue(new Error("health read failed"));
    render(<HealthGrid />);
    expect(await screen.findByText("health read failed")).toBeTruthy();
    expect(screen.queryByText("Loading…")).toBeNull();
  });
});
