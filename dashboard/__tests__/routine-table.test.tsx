/**
 * RoutineTable — loaded, empty, error and refresh (RA-1109).
 * Reads go through fetchProxyJSON; null means the backend did not answer.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const fetchProxyJSON = vi.fn<(path: string) => Promise<unknown>>();

vi.mock("@/lib/pi-ceo-fetch", () => ({
  fetchProxyJSON: (path: string) => fetchProxyJSON(path),
}));

import RoutineTable from "@/components/control/RoutineTable";

beforeEach(() => {
  fetchProxyJSON.mockReset();
});

afterEach(() => {
  cleanup();
});

function run(session_id: string, status: "success" | "failure" | "timeout" = "success") {
  return {
    routine_name: "nightly",
    repo: "CleanExpo/Pi-Dev-Ops",
    trigger: "cron-nightly",
    status,
    duration_s: 12,
    run_url: "",
    summary: "",
    ts: "2026-09-28T01:00:00.000Z",
    session_id,
    evaluator_score: 8.25,
    push_outcome: "pushed",
  };
}

describe("RoutineTable", () => {
  it("LOADED: renders a run row from the response", async () => {
    fetchProxyJSON.mockResolvedValue({ runs: [run("sess-alpha-1")], total: 1 });
    render(<RoutineTable />);
    expect(await screen.findByText("sess-alpha-1")).toBeTruthy();
    expect(screen.getByText("cron-nightly")).toBeTruthy();
    expect(screen.getByText("8.3")).toBeTruthy();
    expect(screen.getByText("pushed")).toBeTruthy();
    expect(fetchProxyJSON).toHaveBeenCalledWith("/api/routines?limit=10");
  });

  it("EMPTY: shows the explicit no-runs copy", async () => {
    fetchProxyJSON.mockResolvedValue({ runs: [], total: 0 });
    render(<RoutineTable />);
    const empty = await screen.findByText("No runs recorded yet.");
    expect(empty.closest("[data-mc-empty]")?.getAttribute("data-mc-empty")).toBe("no-routine-reports");
    expect(screen.getByText(/built-in\s+scheduler.s jobs do not/)).toBeTruthy();
    expect(screen.queryByText("Loading…")).toBeNull();
  });

  it("ERROR: backend unreachable (null) shows an error, not the empty state", async () => {
    fetchProxyJSON.mockResolvedValue(null);
    render(<RoutineTable />);
    expect(await screen.findByText("Pi-CEO backend unreachable")).toBeTruthy();
    expect(screen.queryByText("No runs recorded yet.")).toBeNull();
    expect(document.querySelector("[data-mc-empty], [data-mc-data]")).toBeNull();
    expect(screen.queryByText("Loading…")).toBeNull();
  });

  it("ERROR: a rejected read shows its message", async () => {
    fetchProxyJSON.mockRejectedValue(new Error("boom"));
    render(<RoutineTable />);
    expect(await screen.findByText("boom")).toBeTruthy();
    expect(screen.queryByText("Loading…")).toBeNull();
  });

  it("Refresh re-fetches and renders the new data", async () => {
    fetchProxyJSON
      .mockResolvedValueOnce({ runs: [run("sess-first")], total: 1 })
      .mockResolvedValueOnce({ runs: [run("sess-second", "failure")], total: 1 });
    render(<RoutineTable />);
    expect(await screen.findByText("sess-first")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "refresh" }));
    expect(await screen.findByText("sess-second")).toBeTruthy();
    expect(screen.queryByText("sess-first")).toBeNull();
    await waitFor(() => expect(fetchProxyJSON).toHaveBeenCalledTimes(2));
  });

  it("Refresh that fails replaces the table with an error, not stale rows", async () => {
    fetchProxyJSON
      .mockResolvedValueOnce({ runs: [run("sess-first")], total: 1 })
      .mockResolvedValueOnce(null);
    render(<RoutineTable />);
    expect(await screen.findByText("sess-first")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "refresh" }));
    expect(await screen.findByText("Pi-CEO backend unreachable")).toBeTruthy();
    expect(screen.queryByText("sess-first")).toBeNull();
  });
});
