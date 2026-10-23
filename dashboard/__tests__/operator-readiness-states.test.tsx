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
});
