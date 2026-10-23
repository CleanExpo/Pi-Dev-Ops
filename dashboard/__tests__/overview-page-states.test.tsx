/**
 * /overview Agents On-Shift panel — a failed sessions read is "unavailable",
 * never "No active builds." or "0 active". A true empty success still says so.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const observations = vi.fn();

vi.mock("@/hooks/useOperatorObservations", () => ({
  useOperatorObservations: () => observations(),
}));
vi.mock("@/components/control/OperatorReadiness", () => ({
  OperatorReadiness: () => null,
}));

import OverviewPage from "@/app/(main)/overview/page";

const base = { health: null, sessions: [], healthError: false, checkedAt: null };

afterEach(() => {
  cleanup();
  observations.mockReset();
});

describe("overview page — Agents On-Shift", () => {
  it("ERROR: a failed sessions read says builds unavailable, never 'No active builds' or '0 active'", () => {
    observations.mockReturnValue({ ...base, sessionsError: true, sessionsLoaded: true });
    render(<OverviewPage />);
    expect(screen.getByText("Builds unavailable.")).toBeTruthy();
    expect(screen.queryByText("No active builds.")).toBeNull();
    expect(screen.queryByText("0 active")).toBeNull();
  });

  it("EMPTY: a successful read with nothing running still says no active builds", () => {
    observations.mockReturnValue({ ...base, sessionsError: false, sessionsLoaded: true });
    render(<OverviewPage />);
    expect(screen.getByText("No active builds.")).toBeTruthy();
    expect(screen.getByText("0 active")).toBeTruthy();
  });
});
