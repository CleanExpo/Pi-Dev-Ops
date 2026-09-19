import React from "react";
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FixSessionLive } from "@/components/control/HealthGrid";

class MockEventSource {
  static latest: MockEventSource;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  close = vi.fn();
  constructor() { MockEventSource.latest = this; }
}

beforeEach(() => {
  vi.stubGlobal("EventSource", MockEventSource);
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, headers: new Headers(), json: async () => [] })));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const mount = async () => {
  await act(async () => { render(<FixSessionLive sessionId="test-session" findingTitle="Finding" onClose={() => {}} />); });
};

describe("fix session completion evidence", () => {
  it.each([{ type: "done" }, { type: "closed", reason: "session_complete" }, { type: "log", text: "=== SESSION COMPLETE ===" }])(
    "does not infer success from a log or transport event: %j", async (event) => {
      await mount();
      act(() => MockEventSource.latest.onmessage?.({ data: JSON.stringify(event) }));
      expect(screen.queryByText("Complete", { exact: true })).not.toBeInTheDocument();
      expect(screen.queryByText("Reported complete", { exact: true })).not.toBeInTheDocument();
    },
  );

  it.each(["blocked", "stalled", "interrupted", "error", "failed", "killed"])(
    "surfaces %s from authoritative session state and preserves it on stream loss", async (status) => {
      vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, headers: new Headers(), json: async () => [{ id: "test-session", status }] })));
      await mount();
      expect(screen.getByText(`Session ended: ${status}`, { exact: false })).toBeInTheDocument();
      act(() => MockEventSource.latest.onerror?.());
      expect(screen.getByText(`Session ended: ${status}`, { exact: false })).toBeInTheDocument();
      expect(screen.queryByText("Complete", { exact: true })).not.toBeInTheDocument();
    },
  );

  it("shows reported completion only after a session status response", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, headers: new Headers(), json: async () => [{ id: "test-session", status: "complete" }] })));
    await mount();
    expect(screen.getByText("Reported complete", { exact: true })).toBeInTheDocument();
  });

  it("does not assert the build is running after the stream disconnects", async () => {
    await mount();
    act(() => MockEventSource.latest.onerror?.());
    expect(screen.queryByText(/backend still running|Build continues on server/)).not.toBeInTheDocument();
  });
});
