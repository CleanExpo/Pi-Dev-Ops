/**
 * /routines page — a failed read says "couldn't check", never zero runs.
 * Live it rendered "ROUTINES (0) / TODAY 0 / No runs recorded yet" beside
 * "HTTP 401". A true empty success must still show the empty message.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const fetchProxy = vi.fn();

vi.mock("@/lib/pi-ceo-fetch", () => ({
  fetchProxy: (path: string) => fetchProxy(path),
}));

import RoutinesPage from "@/app/(main)/routines/page";

afterEach(() => {
  cleanup();
  fetchProxy.mockReset();
});

describe("routines page", () => {
  it("ERROR: an HTTP 401 says couldn't check, with no zero counts or empty message", async () => {
    fetchProxy.mockResolvedValue({ ok: false, reason: "http", upstreamStatus: 401 });
    render(<RoutinesPage />);
    expect(await screen.findByText("Couldn't check routines: HTTP 401")).toBeTruthy();
    expect(screen.queryByText("Today")).toBeNull();
    expect(screen.queryByText(/\(0\)/)).toBeNull();
    expect(screen.queryByText(/0 total/)).toBeNull();
    expect(screen.queryByText(/No runs recorded yet/)).toBeNull();
    expect(screen.queryByText(/No routine runs recorded yet/)).toBeNull();
  });

  it("IN FLIGHT: before the read settles, the first paint shows no zero counts", () => {
    fetchProxy.mockReturnValue(new Promise(() => {}));
    render(<RoutinesPage />);
    expect(screen.getByText(/Loading/)).toBeTruthy();
    expect(screen.queryByText("Today")).toBeNull();
    expect(screen.queryByText(/\(0\)/)).toBeNull();
    expect(screen.queryByText(/0 total/)).toBeNull();
    expect(screen.queryByText(/No runs recorded yet/)).toBeNull();
  });

  it("STALE: a failed refresh after a good read keeps the last counts beside the error", async () => {
    const run = {
      routine_name: "daily",
      repo: "CleanExpo/Pi-Dev-Ops",
      trigger: "cron",
      status: "success",
      duration_s: 3,
      run_url: "",
      summary: "",
      ts: new Date().toISOString(),
    };
    fetchProxy.mockResolvedValueOnce({ ok: true, data: { runs: [run], total: 1 } });
    fetchProxy.mockResolvedValueOnce({ ok: false, reason: "http", upstreamStatus: 503 });
    render(<RoutinesPage />);
    expect(await screen.findByText(/1 total/)).toBeTruthy();
    fireEvent.click(screen.getByText("REFRESH"));
    expect(await screen.findByText(/Couldn't check routines: HTTP 503/)).toBeTruthy();
    expect(screen.getByText(/1 total/)).toBeTruthy();
    expect(screen.getByText("Today")).toBeTruthy();
    expect(screen.getByText(/Showing the last good check/)).toBeTruthy();
  });

  it("EMPTY: a successful read with no runs still says none recorded", async () => {
    fetchProxy.mockResolvedValue({ ok: true, data: { runs: [], total: 0 } });
    render(<RoutinesPage />);
    expect(await screen.findByText("No routine runs recorded yet.")).toBeTruthy();
    expect(screen.getByText(/0 total/)).toBeTruthy();
    expect(screen.queryByText(/Couldn't check routines/)).toBeNull();
  });
});
