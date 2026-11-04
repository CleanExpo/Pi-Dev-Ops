/**
 * The /control wall rendered over stubbed feeds. Revenue never shows a number,
 * campaign hops stay "not connected", failed GitHub reads read "unknown", and
 * the ticker never says all clear while sources are down.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CommandWall from "@/components/control/wall/CommandWall";
import { resetSources } from "@/lib/boards/sources";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const NOW = new Date().toISOString();
const WALL = {
  generated_at: NOW,
  banner: { red: 0, grey: 1 },
  fleet: {
    status: "ok", reason: "", others: [],
    machines: [
      { host: "Phills-Mac-mini", chip: "GREEN", reason: "reporting", ageSeconds: 12, load1: 0.8, selfReported: true,
        agents: [{ runtime: "codex", state: "busy", chip: "GREEN", ageSeconds: 4 }] },
      { host: "Phill_Desktop", chip: "GREY", reason: "no signal", ageSeconds: 900, load1: null, selfReported: true, agents: [] },
    ],
  },
  stations: [],
};

function router(overrides: Record<string, () => Response> = {}) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    for (const [key, make] of Object.entries(overrides)) if (url.includes(key)) return make();
    if (url.includes("/api/mesh-fleet/wall")) return json(WALL);
    if (url.includes("/api/mesh-fleet")) return json({ status: "unavailable", checkedAt: NOW, reason: "mesh secret not configured" });
    if (url.includes("/api/flow-board")) {
      return json({ ok: false, checked_at: NOW, error: "GitHub unavailable: GITHUB_TOKEN not set",
        columns: { shipped: [], audit: [], phill: [], aging: [] }, repo: new URL(url, "http://x").searchParams.get("repo"),
        pull_requests: { status: "unavailable", reason: "GITHUB_TOKEN not set" }, ci: { status: "unavailable", reason: "GITHUB_TOKEN not set" } });
    }
    return json({ error: "not stubbed" }, 503);
  });
}

beforeEach(() => resetSources());
afterEach(() => {
  vi.unstubAllGlobals();
  cleanup();
  resetSources();
});

describe("CommandWall", () => {
  it("renders the five screens with the machines and honest empty states", async () => {
    vi.stubGlobal("fetch", router());
    render(<CommandWall />);
    expect(screen.getByRole("heading", { name: "Mission Control" })).toBeTruthy();
    expect(await screen.findByText("Mac Mini")).toBeTruthy();
    expect(screen.getByText("PC")).toBeTruthy();
    expect(screen.getByText(/codex · busy/)).toBeTruthy();

    const revenue = screen.getByRole("region", { name: "Revenue and funnel" });
    expect(within(revenue).getByText(/No revenue or funnel source is connected/)).toBeTruthy();
    expect(within(revenue).queryByText(/\$|\d/)).toBeNull();

    const flow = screen.getByRole("region", { name: "CRM to Synthex campaign flow" });
    expect(within(flow).getAllByText("not connected").length).toBeGreaterThanOrEqual(5);
    expect(within(flow).queryByText("connected")).toBeNull();
  });

  it("a GitHub read that failed shows unknown and the reason, never 0 open PRs", async () => {
    vi.stubGlobal("fetch", router());
    render(<CommandWall />);
    const prs = screen.getByRole("region", { name: "PR pipeline" });
    expect((await within(prs).findAllByText(/unavailable: GITHUB_TOKEN not set/)).length).toBe(6);
    expect(within(prs).queryByText("0")).toBeNull();
    expect(within(prs).getAllByText("unknown").length).toBe(24);
  });

  it("the ticker names failed sources and never claims all clear while they are down", async () => {
    vi.stubGlobal("fetch", router());
    render(<CommandWall />);
    const ticker = screen.getByRole("region", { name: "Alerts and incidents" });
    // Visible items appear once; the seamless-loop copy is aria-hidden.
    const named = await within(ticker).findAllByText(/Fleet job claims not connected: mesh secret not configured/);
    expect(named.filter((el) => el.closest("[aria-hidden='true']") === null)).toHaveLength(1);
    expect(within(ticker).getAllByText(/PC: no signal/).length).toBeGreaterThanOrEqual(1);
    expect(within(ticker).queryByText(/No active alerts/)).toBeNull();
  });
});
