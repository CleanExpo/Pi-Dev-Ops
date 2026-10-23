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
    expect(screen.queryByText("0 sessions")).toBeNull();
  });

  it("IN FLIGHT: a sessions read that has not settled shows no counts", () => {
    observations.mockReturnValue({ ...base, sessionsError: false, sessionsLoaded: false });
    render(<OverviewPage />);
    expect(screen.getAllByText("Checking sessions...").length).toBeGreaterThan(0);
    expect(screen.queryByText("0 active")).toBeNull();
    expect(screen.queryByText("0 sessions")).toBeNull();
    expect(screen.getAllByText("unknown").length).toBe(2);
  });

  it("REFRESH: an unsettled refresh after an empty read says checking, never '0 active'", () => {
    observations.mockReturnValue({ ...base, sessionsError: false, sessionsLoaded: true, sessionsChecking: true });
    render(<OverviewPage />);
    expect(screen.getAllByText("Checking sessions...").length).toBe(2);
    expect(screen.queryByText("No active builds.")).toBeNull();
    expect(screen.queryByText("0 active")).toBeNull();
    expect(screen.queryByText("0 sessions")).toBeNull();
    expect(screen.getAllByText("checking").length).toBe(2);
  });

  it("REFRESH NONEMPTY: during a re-read, last seen sessions are labelled as being checked", () => {
    const building = { id: "s1", status: "building", started: "2026-10-23T00:00:00Z", repo: "x", lastPhase: "" };
    observations.mockReturnValue({ ...base, sessions: [building], sessionsError: false, sessionsLoaded: true, sessionsChecking: true });
    render(<OverviewPage />);
    expect(screen.queryByText("1 active")).toBeNull();
    expect(screen.queryByText("1 sessions")).toBeNull();
    expect(screen.getByText("1 active, checking")).toBeTruthy();
    expect(screen.getByText("1 sessions, checking")).toBeTruthy();
  });

  it("HEALTH REFRESH: during a /health re-read, health-derived counts are marked as being checked", () => {
    const health = { status: "ok", sessions: { active: 0, max: 4 }, autonomy: { armed: false, poll_count: 7, seconds_since_last_poll: 5 } };
    observations.mockReturnValue({ ...base, health, healthChecking: true, sessionsError: false, sessionsLoaded: true, sessionsChecking: false });
    render(<OverviewPage />);
    expect(screen.queryByText("0 / 4")).toBeNull();
    expect(screen.getByText("0 / 4, checking")).toBeTruthy();
    // Poll count shows in the Polls chip and the Autonomy detail; both are marked.
    expect(screen.getAllByText("7, checking").length).toBe(2);
    expect(screen.queryByText("7")).toBeNull();
  });

  it("HEALTH DETAIL REFRESH: during a /health re-read, status, state, services and a null last poll are marked", () => {
    const health = { status: "ok", sessions: { active: 0, max: 4 }, autonomy: { armed: false, poll_count: 7, seconds_since_last_poll: null } };
    observations.mockReturnValue({ ...base, health, healthChecking: true, sessionsError: false, sessionsLoaded: true, sessionsChecking: false });
    render(<OverviewPage />);
    expect(screen.queryByText("Never")).toBeNull();
    expect(screen.getByText("Never, checking")).toBeTruthy();
    expect(screen.queryByText("OK")).toBeNull();
    expect(screen.getByText("OK, checking")).toBeTruthy();
    expect(screen.queryByText("Disarmed")).toBeNull();
    expect(screen.getByText("Disarmed, checking")).toBeTruthy();
    expect(screen.getByText("Services, checking")).toBeTruthy();
  });

  it("HEALTH LEDE: during a /health re-read, the header does not call the overview live", () => {
    const health = { status: "ok", sessions: { active: 0, max: 4 } };
    observations.mockReturnValue({ ...base, health, healthChecking: true, sessionsError: false, sessionsLoaded: true, sessionsChecking: false });
    render(<OverviewPage />);
    expect(screen.queryByText(/^Live system overview/)).toBeNull();
    expect(screen.getByText(/Checking the backend again/)).toBeTruthy();
  });

  it("HEALTH FAILED: a failed /health read says unavailable, never 'Connecting to backend'", () => {
    observations.mockReturnValue({ ...base, healthError: true, sessionsError: false, sessionsLoaded: true, sessionsChecking: false });
    render(<OverviewPage />);
    expect(screen.queryByText(/Connecting to backend/)).toBeNull();
    expect(screen.getByText("Health unavailable.")).toBeTruthy();
  });

  it("SESSIONS LIVE REFRESH: during a sessions re-read, a retained building session is not called live", () => {
    const building = { id: "s1", status: "building", started: "2026-10-23T00:00:00Z", repo: "x", lastPhase: "" };
    observations.mockReturnValue({ ...base, sessions: [building], sessionsError: false, sessionsLoaded: true, sessionsChecking: true, healthChecking: false });
    render(<OverviewPage />);
    expect(screen.queryByText("LIVE")).toBeNull();
    expect(screen.getByText("LIVE, checking")).toBeTruthy();
    expect(screen.queryByText("building")).toBeNull();
    expect(screen.getByText("building, checking")).toBeTruthy();
    expect(screen.getByText(/Checking the backend again/)).toBeTruthy();
  });

  it("EMPTY: a successful read with nothing running still says no active builds", () => {
    observations.mockReturnValue({ ...base, sessionsError: false, sessionsLoaded: true, sessionsChecking: false });
    render(<OverviewPage />);
    expect(screen.getByText("No active builds.")).toBeTruthy();
    expect(screen.getByText("0 active")).toBeTruthy();
    expect(screen.getByText("0 sessions")).toBeTruthy();
  });
});
