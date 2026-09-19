import React from "react";
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
vi.mock("@/components/control/KillSwitchPanel", () => ({ default: () => null }));
import SwarmPanel from "@/components/control/SwarmPanel";
import ModelBadge from "@/components/control/ModelBadge";
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });
describe("control telemetry refresh", () => {
  it.each([
    { Component: SwarmPanel, interval: 30_000, label: "ACTIVE", payload: { state: "ACTIVE", autonomous_prs_today: 1, autonomous_prs_limit: 3, green_merges: 1, green_merges_target: 20 } },
    { Component: ModelBadge, interval: 60_000, label: "Observed model test", payload: { score: 90, model: "Observed model test", model_id: "test-model", sdk_mode: null, source: "backend" } },
  ])("withdraws stale $label when a refresh hangs", async ({ Component, interval, label, payload }) => {
    vi.useFakeTimers();
    let hangs = false;
    vi.stubGlobal("fetch", vi.fn(async (_url: string, options?: RequestInit) => {
      if (!hangs) return { ok: true, json: async () => payload };
      return new Promise<Response>((_, reject) => options?.signal?.addEventListener("abort", () => reject(new Error("timeout"))));
    }));
    render(<Component />);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(screen.getByText(label, { exact: true })).toBeInTheDocument();
    hangs = true;
    await act(async () => { await vi.advanceTimersByTimeAsync(interval + 10_000); });
    expect(screen.queryByText(label, { exact: true })).not.toBeInTheDocument();
  });
});
