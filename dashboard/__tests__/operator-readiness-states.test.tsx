/**
 * OperatorReadiness — a service status from the previous /health read is not restated as current during a re-read.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { OperatorReadiness } from "@/components/control/OperatorReadiness";

afterEach(() => cleanup());

const health = { status: "ok" } as never;

describe("OperatorReadiness service chip", () => {
  it("HEALTH REFRESH: during a re-read, the last reading is marked as being checked", () => {
    render(<OperatorReadiness health={health} sessions={[]} healthError={false} sessionsError={false} healthChecking />);
    expect(screen.queryByText("Service reachable")).toBeNull();
    expect(screen.getByText("Service reachable, checking")).toBeTruthy();
  });

  it("SETTLED: a settled ok read still says reachable", () => {
    render(<OperatorReadiness health={health} sessions={[]} healthError={false} sessionsError={false} healthChecking={false} />);
    expect(screen.getByText("Service reachable")).toBeTruthy();
  });

  it("SESSIONS REFRESH: during a sessions re-read, a retained blocked session is marked as being checked", () => {
    const blocked = { id: "s2", status: "blocked", started: "2026-10-23T00:00:00Z", repo: "x" } as never;
    render(<OperatorReadiness health={health} sessions={[blocked]} healthError={false} sessionsError={false} healthChecking={false} sessionsChecking />);
    expect(screen.queryByText("Work blocked")).toBeNull();
    expect(screen.getByText("Work blocked, checking")).toBeTruthy();
    expect(screen.queryByText("blocked")).toBeNull();
    expect(screen.getByText("blocked, checking")).toBeTruthy();
  });

  it("HEALTH DETAIL REFRESH: during a re-read, Generation, its blockers and Model documentation are marked as last reading", () => {
    const h = { status: "ok", generation: { status: "blocked", blockers: ["quota"] }, model_documentation: { status: "fresh" } } as never;
    render(<OperatorReadiness health={h} sessions={[]} healthError={false} sessionsError={false} healthChecking />);
    expect(screen.queryByText("blocked")).toBeNull();
    expect(screen.getByText("blocked, checking")).toBeTruthy();
    expect(screen.queryByText("fresh")).toBeNull();
    expect(screen.getByText("fresh, checking")).toBeTruthy();
    expect(screen.queryByText("quota")).toBeNull();
    expect(screen.getByText("quota, checking")).toBeTruthy();
    expect(screen.getByText("Checking again; the values below are from the last health reading.")).toBeTruthy();
  });

  it("HEALTH DETAIL SETTLED: a settled read states Generation and Model documentation plainly", () => {
    const h = { status: "ok", generation: { status: "blocked", blockers: [] }, model_documentation: { status: "fresh" } } as never;
    render(<OperatorReadiness health={h} sessions={[]} healthError={false} sessionsError={false} healthChecking={false} />);
    expect(screen.getByText("blocked")).toBeTruthy();
    expect(screen.getByText("fresh")).toBeTruthy();
    expect(screen.queryByText(/Checking again/)).toBeNull();
  });
});
