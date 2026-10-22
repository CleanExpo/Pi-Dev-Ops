// Loop Cockpit "Needs me" — a failed Linear or session-store read must never
// leave the panel saying "Nothing needs you — the loop is healthy."
// (review round 2 P1, mc-truth-1: the page computed the unavailable state but
// never passed it to deriveNeeds, so the all-clear showed over failed reads.)

import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup, waitFor } from "@testing-library/react";
import LoopCockpit from "@/app/(main)/loop/page";
import { deriveNeeds } from "@/lib/control/loop-needs";

const FAILED = {
  ts: new Date().toISOString(),
  throughput: { hourly: null },
  active_sessions: null,
  recent_completions: null,
  queue: { available: false, error: "Linear rate limited", urgent: null, high: null, next_issue_id: null },
  pulse: { available: false, error: "Linear rate limited", comments_today: null },
  observability: { fully_observed: false, degraded_components: [], actions: [] },
};

const GOOD = {
  ts: new Date().toISOString(),
  throughput: { hourly: Array.from({ length: 24 }, () => 0) },
  active_sessions: [],
  recent_completions: [],
  queue: { available: true, urgent: 0, high: 0, next_issue_id: null },
  pulse: { available: true, comments_today: 0 },
  observability: { fully_observed: true, degraded_components: [], actions: [] },
};

function mockLive(body: unknown) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => String(url).includes("/api/mission-control/live")
    ? new Response(JSON.stringify(body), { status: 200 })
    : new Response("nope", { status: 404 })));
}

async function settle() {
  const synced = await screen.findByText(/^synced/);
  await waitFor(() => expect(synced.textContent).not.toMatch(/—/));
}

function needsPanel(): HTMLElement {
  return screen.getByRole("region", { name: "Needs me" });
}

describe("Loop Cockpit — Needs me over failed reads", () => {
  afterEach(() => { vi.unstubAllGlobals(); cleanup(); });

  it("lists the failed reads instead of the all-clear", async () => {
    mockLive(FAILED);
    render(<LoopCockpit />);
    await settle();
    const text = needsPanel().textContent ?? "";
    expect(text).not.toMatch(/Nothing needs you/);
    expect(text).toMatch(/Linear queue unavailable — Linear rate limited/);
    expect(text).toMatch(/Session store unavailable — running work is unknown/);
  });

  it.each(["active_sessions", "recent_completions", "hourly"])("one failed session-store read (%s) is enough to withhold the all-clear", async (field) => {
    const body = field === "hourly" ? { ...GOOD, throughput: { hourly: null } } : { ...GOOD, [field]: null };
    mockLive(body);
    render(<LoopCockpit />);
    await settle();
    const text = needsPanel().textContent ?? "";
    expect(text).not.toMatch(/Nothing needs you/);
    expect(text).toMatch(/Session store unavailable — running work is unknown/);
  });

  it("positive control: good reads still show the all-clear", async () => {
    mockLive(GOOD);
    render(<LoopCockpit />);
    await settle();
    const text = needsPanel().textContent ?? "";
    expect(text).toMatch(/Nothing needs you/);
    expect(text).not.toMatch(/unavailable/);
  });
});

describe("deriveNeeds — availability inputs", () => {
  it("adds an error-level need for each failed read", () => {
    const needs = deriveNeeds({ queueUnavailable: "Linear rate limited", sessionStoreDown: true });
    expect(needs.map((n) => n.text)).toEqual([
      "Linear queue unavailable — Linear rate limited",
      "Session store unavailable — running work is unknown",
    ]);
    expect(needs.every((n) => n.color === "var(--error)")).toBe(true);
  });

  it("adds nothing when the reads succeeded", () => {
    expect(deriveNeeds({ queueUnavailable: null, sessionStoreDown: false })).toEqual([]);
  });
});
