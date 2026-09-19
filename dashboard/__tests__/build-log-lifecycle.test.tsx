import React from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import BuildsPage from "@/app/(main)/builds/page";

class MockEventSource {
  static instances: MockEventSource[] = [];
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  close = vi.fn();
  constructor() { MockEventSource.instances.push(this); }
}

const originalScroll = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollIntoView");
beforeEach(() => {
  vi.useFakeTimers();
  MockEventSource.instances = [];
  vi.stubGlobal("EventSource", MockEventSource);
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { value: vi.fn(), configurable: true });
});
afterEach(() => {
  cleanup(); vi.unstubAllGlobals(); vi.useRealTimers();
  if (originalScroll) Object.defineProperty(HTMLElement.prototype, "scrollIntoView", originalScroll);
  else Reflect.deleteProperty(HTMLElement.prototype, "scrollIntoView");
});

async function openBuild(status: string) {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, headers: new Headers(), json: async () => [{
    id: "session-1", repo: "org/project", status, started: 1789780000, lines: 1,
    parent: null, last_phase: "evaluate", evaluator_score: null, retry_count: 0, evaluator_status: "pending",
  }] })));
  await act(async () => { render(<BuildsPage />); });
  fireEvent.click(screen.getByText("org/project"));
  return MockEventSource.instances[0];
}

describe("build log connection lifecycle", () => {
  it.each(["blocked", "stalled", "interrupted", "error"])("does not reconnect a %s session", async (status) => {
    const stream = await openBuild(status);
    act(() => stream.onerror?.());
    await act(async () => { await vi.advanceTimersByTimeAsync(2100); });
    expect(MockEventSource.instances).toHaveLength(1);
  });

  it("cancels a pending reconnect when the log panel is collapsed", async () => {
    const stream = await openBuild("building");
    act(() => stream.onerror?.());
    fireEvent.click(screen.getByText("org/project"));
    await act(async () => { await vi.advanceTimersByTimeAsync(2100); });
    expect(MockEventSource.instances).toHaveLength(1);
  });

  it("closes the transport on the server's closed event", async () => {
    const stream = await openBuild("building");
    act(() => stream.onmessage?.({ data: JSON.stringify({ type: "closed", reason: "session_complete" }) }));
    expect(stream.close).toHaveBeenCalled();
  });
});
