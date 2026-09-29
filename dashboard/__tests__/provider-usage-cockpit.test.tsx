/**
 * ProviderUsageCockpit — loaded, empty and error states (AAA check 7, MC-16).
 * Reads /api/command-centre/provider-usage with fetch. An unknown usage figure
 * must never render as a filled meter.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProviderUsageCockpit } from "@/components/command-centre/provider-usage/ProviderUsageCockpit";

function serve(body: unknown, status = 200) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status })));
}

const provider = (over: Record<string, unknown>) => ({
  id: "claude", label: "Anthropic API", planType: "Metered API route", resetCadence: "provider limits",
  state: "available", truthLevel: "live", bestUseLane: "deep_reasoning", fallbackProvider: "openai",
  missingSetupReason: null, usagePct: 40, lastChecked: "2026-09-29T00:00:00Z", ...over,
});

const payload = (providers: unknown[], routing: unknown[] = []) => ({
  source: "cc:provider-usage", generatedAt: "2026-09-29T00:00:00Z",
  summary: { total: providers.length, available: providers.length, watching: 0, nearLimit: 0, blocked: 0, unknown: 0 },
  providers, routing,
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ProviderUsageCockpit", () => {
  it("LOADED: renders each provider's state and usage, and the routing lanes", async () => {
    serve(payload([provider({})], [{ lane: "deep_reasoning", recommended: "claude", reason: "healthy" }]));
    render(<ProviderUsageCockpit />);
    expect(await screen.findByTestId("provider-state-claude")).toBeTruthy();
    expect(screen.getByRole("meter", { name: "Anthropic API usage" }).getAttribute("aria-valuenow")).toBe("40");
    expect(screen.getByTestId("moa-routing-badge").textContent).toContain("1/1 lanes routable");
    expect(document.querySelector('[data-mc-data="provider-usage"]')).not.toBeNull();
  });

  it("EMPTY: unknown usage is labelled unknown, never a filled meter", async () => {
    serve(payload([provider({ state: "unknown", truthLevel: "unavailable", usagePct: null,
      missingSetupReason: "Runtime usage telemetry unavailable" })]));
    render(<ProviderUsageCockpit />);
    expect(await screen.findByRole("img", { name: "Anthropic API usage unknown" })).toBeTruthy();
    expect(screen.queryByRole("meter")).toBeNull();
    expect(screen.getByText(/Runtime usage telemetry unavailable/)).toBeTruthy();
  });

  it("ERROR: a non-OK response shows the degraded banner and no provider data", async () => {
    serve({ error: "boom" }, 500);
    render(<ProviderUsageCockpit />);
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText(/provider_usage_http_500/).textContent).toContain("last successful read, not current");
    expect(screen.queryByText(/static seed/)).toBeNull();
    expect(document.querySelector("[data-mc-data]")).toBeNull();
  });

  it("ERROR: a rejected fetch shows the degraded banner with its reason", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("offline"); }));
    render(<ProviderUsageCockpit />);
    expect(await screen.findByText(/\(offline\)/)).toBeTruthy();
    expect(screen.queryByTestId("provider-state-claude")).toBeNull();
  });
});
