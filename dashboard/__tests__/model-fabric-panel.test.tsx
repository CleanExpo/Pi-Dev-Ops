/**
 * ModelFabricPanel — loaded, empty and error states (RA-1109).
 * A failed status read must say so; it must never render as "DISABLED".
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/control/ModelBadge", () => ({ default: () => null }));

import ModelFabricPanel from "@/components/control/ModelFabricPanel";

afterEach(() => {
  vi.unstubAllGlobals();
  cleanup();
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("ModelFabricPanel", () => {
  it("LOADED: renders lanes, totals and the latest routed call", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse({
          enabled: true,
          healthy: true,
          models_available: 7,
          lanes: { generator: { model: "sonnet-lane-model-x", banned: false } },
          totals: { calls: 4, failures: 1, fallbacks: 2, strengthened: 0 },
          last_call: {
            ts: 1,
            role: "evaluator",
            lane: "generator",
            requested_model: "req-model-y",
            served_model: "served-model-z",
            provider: "anthropic",
            latency_ms: 321,
            ok: true,
            attempts: ["served-model-z"],
          },
        }),
      ),
    );
    render(<ModelFabricPanel />);
    expect(await screen.findByText("sonnet-lane-model-x")).toBeTruthy();
    expect(screen.getByText("generator")).toBeTruthy();
    expect(screen.getByText("APPROVED")).toBeTruthy();
    expect(screen.getByText(/HEALTHY/)).toBeTruthy();
    expect(screen.getByText("25%")).toBeTruthy();
    expect(screen.getByText("served: served-model-z")).toBeTruthy();
    expect(screen.queryByText(/Loading model fabric/)).toBeNull();
  });

  it("EMPTY: shows the explicit no-routed-call copy", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ enabled: true, healthy: true, models_available: 0, lanes: {}, last_call: null, totals: { calls: 0, failures: 0, fallbacks: 0, strengthened: 0 } })),
    );
    render(<ModelFabricPanel />);
    expect(
      await screen.findByText("No routed call recorded since this Pi-CEO process started."),
    ).toBeTruthy();
    expect(screen.queryByText(/Loading model fabric/)).toBeNull();
  });

  it("ERROR: a rejected fetch shows the error, not an endless spinner", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("network down"); }));
    render(<ModelFabricPanel />);
    expect(await screen.findByText("network down")).toBeTruthy();
    expect(screen.queryByText(/Loading model fabric/)).toBeNull();
  });

  it("ERROR: a 500 carrying an error field shows that error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ enabled: false, healthy: false, error: "Pi-CEO unavailable" }, 503)),
    );
    render(<ModelFabricPanel />);
    expect(await screen.findByText("Pi-CEO unavailable")).toBeTruthy();
  });

  it("ERROR: a 500 without an error field is reported as a failure, not as DISABLED", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ detail: "Internal Server Error" }, 500)),
    );
    render(<ModelFabricPanel />);
    expect(await screen.findByText(/HTTP 500/)).toBeTruthy();
    expect(screen.queryByText(/Loading model fabric/)).toBeNull();
  });
});
