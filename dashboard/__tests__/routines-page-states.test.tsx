/**
 * /routines page — a failed read says "couldn't check", never zero runs.
 * Live it rendered "ROUTINES (0) / TODAY 0 / No runs recorded yet" beside
 * "HTTP 401". A true empty success must still show the empty message.
 */
import { cleanup, render, screen } from "@testing-library/react";
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

  it("EMPTY: a successful read with no runs still says none recorded", async () => {
    fetchProxy.mockResolvedValue({ ok: true, data: { runs: [], total: 0 } });
    render(<RoutinesPage />);
    expect(await screen.findByText("No routine runs recorded yet.")).toBeTruthy();
    expect(screen.queryByText(/Couldn't check routines/)).toBeNull();
  });
});
