import React from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AgentRolesPanel from "@/components/control/AgentRolesPanel";
import BuildsPage from "@/app/(main)/builds/page";

class MockEventSource {
  static latest: MockEventSource;
  onmessage: ((event: { data: string }) => void) | null = null;
  close = vi.fn();
  constructor() { MockEventSource.latest = this; }
}
const originalScroll = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollIntoView");
beforeEach(() => {
  vi.stubGlobal("EventSource", MockEventSource);
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { value: vi.fn(), configurable: true });
});
afterEach(() => {
  cleanup(); vi.unstubAllGlobals();
  if (originalScroll) Object.defineProperty(HTMLElement.prototype, "scrollIntoView", originalScroll);
  else Reflect.deleteProperty(HTMLElement.prototype, "scrollIntoView");
});
function sessions(cost: unknown, basis = "unknown") {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, headers: new Headers(), json: async () => [{
    id: "session-1", repo: "org/project", status: "building", started: 1789780000, lines: 1,
    parent: null, last_phase: "evaluate", evaluator_score: null, retry_count: 0, evaluator_status: "pending",
    phase_metrics: { generate: { duration_s: 12, cost_usd: cost, cost_basis: basis, cost_verified: false } },
  }] })));
}
describe("phase cost evidence", () => {
  it.each([null, undefined, NaN, Infinity, -1, "0"])("roles preserve an unmeasured or invalid cost %s", async (cost) => {
    sessions(cost, "reported_usage");
    await act(async () => { render(<AgentRolesPanel />); });
    expect(screen.getByText(/last: org\/project/)).toHaveTextContent("cost unknown");
    expect(screen.queryByText(/\$0\.0000|\$NaN|\$Infinity/)).not.toBeInTheDocument();
  });
  it("does not elevate an explicit unknown basis into a zero-dollar observation", async () => {
    sessions(0, "unknown");
    await act(async () => { render(<AgentRolesPanel />); });
    expect(screen.getByText(/last: org\/project/)).toHaveTextContent("cost unknown");
  });
  it.each([0, 0.125])("labels a finite amount %s as reported usage with unverified billing", async (cost) => {
    sessions(cost, "reported_usage");
    await act(async () => { render(<AgentRolesPanel />); });
    expect(screen.getByText(/last: org\/project/)).toHaveTextContent(`reported usage $${cost.toFixed(4)} (billing unverified)`);
  });
  it.each(["null", "1e999", "-1", '"0"', "0"])("build metrics never turn %s unknown/invalid cost into a zero-dollar tooltip", async (cost) => {
    sessions(null);
    await act(async () => { render(<BuildsPage />); });
    fireEvent.click(screen.getByText("org/project"));
    act(() => MockEventSource.latest.onmessage?.({ data: `{"i":0,"type":"phase_metric","phase":"generate","duration_s":12,"cost_usd":${cost},"cost_basis":"${cost === "0" ? "unknown" : "reported_usage"}","cost_verified":false,"text":"metric","ts":0}` }));
    expect(screen.getByTitle(/Generate: 12s/)).toHaveAttribute("title", expect.stringContaining("cost unknown"));
    expect(screen.getByTitle(/Generate: 12s/)).not.toHaveAttribute("title", expect.stringContaining("$0.0000"));
  });
  it("build metrics qualify finite reported usage instead of claiming billed cost", async () => {
    sessions(null);
    await act(async () => { render(<BuildsPage />); });
    fireEvent.click(screen.getByText("org/project"));
    act(() => MockEventSource.latest.onmessage?.({ data: JSON.stringify({ i: 0, type: "phase_metric", phase: "generate", duration_s: 12, cost_usd: 0.125, cost_basis: "reported_usage", cost_verified: false, text: "metric", ts: 0 }) }));
    expect(screen.getByTitle(/Generate: 12s/)).toHaveAttribute("title", expect.stringContaining("reported usage $0.1250 (billing unverified)"));
  });
});
