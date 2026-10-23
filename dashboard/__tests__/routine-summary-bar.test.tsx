/**
 * RoutineSummaryBar — "Today" counts runs on the Brisbane calendar day, not the UTC one.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RoutineSummaryBar, type RoutineRun } from "@/components/control/RoutineSummaryBar";

function run(ts: string): RoutineRun {
  return { routine_name: "r", repo: "x", trigger: "cron", status: "success", duration_s: 1, run_url: "", summary: "", ts };
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("RoutineSummaryBar Today count", () => {
  it("BRISBANE DAY: a 08:00 AEST run counts as today at 11:00 AEST, though it is yesterday in UTC", () => {
    const asOf = new Date("2026-10-23T01:00:00Z").getTime(); // 23/10 11:00 AEST
    render(<RoutineSummaryBar runs={[run("2026-10-22T22:00:00Z")]} checking={false} failed={false} asOf={asOf} />);
    expect(screen.getByText("Today").nextSibling?.textContent).toBe("1");
  });

  it("MIDNIGHT STALE: after a failed refresh past midnight, Today counts the last good read's day, labelled", () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-23T14:05:00Z")); // 24/10 00:05 AEST
    const asOf = new Date("2026-10-23T13:56:00Z").getTime(); // 23/10 23:56 AEST, the last good read
    render(<RoutineSummaryBar runs={[run("2026-10-23T13:55:00Z")]} checking={false} failed asOf={asOf} />);
    expect(screen.getByText("Today").nextSibling?.textContent).toBe("1, last good check");
  });

  it("BRISBANE DAY: a run late on the previous Brisbane day is not today", () => {
    const asOf = new Date("2026-10-23T01:00:00Z").getTime(); // 23/10 11:00 AEST
    render(<RoutineSummaryBar runs={[run("2026-10-22T13:59:00Z")]} checking={false} failed={false} asOf={asOf} />); // 22/10 23:59 AEST
    expect(screen.getByText("Today").nextSibling?.textContent).toBe("0");
  });
});
