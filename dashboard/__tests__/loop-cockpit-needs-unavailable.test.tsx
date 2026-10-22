// Loop Cockpit "Needs me" — "Nothing needs you — the loop is healthy." may only
// show when EVERY read the panel depends on succeeded.
//
// Three review rounds each found one more failed read that turned into the
// all-clear: the Linear queue and session store (round 2), then the swarm
// (kill-switch) and autonomy reads (round 3), which the proxy answers with
// HTTP 200 + X-Upstream-Status: 502 when the backend is down. This file serves
// each source failing ALONE in exactly that shape and asserts the all-clear is
// withheld and the matching need appears. deriveNeeds now takes an availability
// entry for every source, so a source nobody reported is unavailable too.

import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup, waitFor } from "@testing-library/react";
import LoopCockpit from "@/app/(main)/loop/page";
import { deriveNeeds, NEEDS_SOURCES, type NeedsAvailability } from "@/lib/control/loop-needs";

const LIVE_GOOD = {
  ts: new Date().toISOString(),
  throughput: { hourly: Array.from({ length: 24 }, () => 0) },
  active_sessions: [],
  recent_completions: [],
  queue: { available: true, urgent: 0, high: 0, next_issue_id: null },
  pulse: { available: true, comments_today: 0 },
  observability: { fully_observed: true, degraded_components: [], actions: [] },
};

const AUTONOMY_GOOD = {
  enabled: true, poll_interval_s: 300, last_poll_at: 1, last_poll_ago_s: 30,
  stale: false, poll_count: 5, poller_iteration_errors: 0, last_iteration_error: null,
};

const SWARM_GOOD = {
  swarm_enabled_env: true, kill_switch_active: false, escalation_lock_active: false,
  panic_count_last_hour: 0, pr_quota: { used: 0, limit: 5 },
};

const ROUTINES_GOOD = { runs: [], total: 0 };

const ENDPOINTS = {
  live: "/api/mission-control/live",
  autonomy: "/api/autonomy/status",
  swarm: "/api/swarm/status",
  routines: "/api/routines",
} as const;
type Endpoint = keyof typeof ENDPOINTS;

const GOOD_BODY: Record<Endpoint, unknown> = {
  live: LIVE_GOOD, autonomy: AUTONOMY_GOOD, swarm: SWARM_GOOD, routines: ROUTINES_GOOD,
};

/** What the proxy's quietFallback sends: 200, a placeholder body, X-Upstream-Status. */
function quietFallback(name: Endpoint): Response {
  const body = name === "live"
    ? { ...LIVE_GOOD, error: "Pi CEO server unreachable" }
    : name === "routines" ? { runs: [], total: 0, error: "Pi CEO server unreachable" }
    : { error: "Pi CEO server unreachable" };
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json", "X-Upstream-Status": "502" },
  });
}

/** Every endpoint answers good unless it is in `failed` or overridden in `bodies`. */
function serve(failed: Endpoint[] = [], bodies: Partial<Record<Endpoint, unknown>> = {}) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const name = (Object.keys(ENDPOINTS) as Endpoint[]).find((k) => String(url).includes(ENDPOINTS[k]));
    if (!name) return new Response("nope", { status: 404 });
    if (failed.includes(name)) return quietFallback(name);
    const body = name in bodies ? bodies[name] : GOOD_BODY[name];
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
}

async function settle() {
  const synced = await screen.findByText(/^synced/);
  await waitFor(() => expect(synced.textContent).not.toMatch(/—/));
}

async function needsText(): Promise<string> {
  render(<LoopCockpit />);
  await settle();
  return screen.getByRole("region", { name: "Needs me" }).textContent ?? "";
}

const ALL_CLEAR = /Nothing needs you/;

const NEED_FOR: Record<Endpoint, RegExp> = {
  live: /Mission Control live read unavailable/,
  autonomy: /Autonomy status unavailable — poller state unknown/,
  swarm: /Swarm status unavailable — kill-switch state unknown/,
  routines: /Loop runs unavailable — recent loop runs unknown/,
};

describe("Loop Cockpit — Needs me withholds the all-clear over any failed read", () => {
  afterEach(() => { vi.unstubAllGlobals(); cleanup(); });

  it("positive control: every read good (autonomy and swarm included) shows the all-clear", async () => {
    serve();
    const text = await needsText();
    expect(text).toMatch(ALL_CLEAR);
    expect(text).not.toMatch(/unavailable/);
  });

  it.each(Object.keys(ENDPOINTS) as Endpoint[])("%s read failed alone (200 + X-Upstream-Status: 502)", async (name) => {
    serve([name]);
    const text = await needsText();
    expect(text).not.toMatch(ALL_CLEAR);
    expect(text).toMatch(NEED_FOR[name]);
  });

  it("reviewer probe: swarm AND autonomy failed, live good", async () => {
    serve(["swarm", "autonomy"]);
    const text = await needsText();
    expect(text).not.toMatch(ALL_CLEAR);
    expect(text).toMatch(NEED_FOR.swarm);
    expect(text).toMatch(NEED_FOR.autonomy);
  });

  it("reviewer probe: swarm only failed, live and autonomy good", async () => {
    serve(["swarm"]);
    const text = await needsText();
    expect(text).not.toMatch(ALL_CLEAR);
    expect(text).toMatch(NEED_FOR.swarm);
    expect(text).not.toMatch(NEED_FOR.autonomy);
  });

  it("a swarm body that does not report the kill-switch is not a read of it", async () => {
    serve([], { swarm: { swarm_enabled_env: true } });
    const text = await needsText();
    expect(text).not.toMatch(ALL_CLEAR);
    expect(text).toMatch(NEED_FOR.swarm);
    // ...and the Swarm panel does not print "Clear" for a kill-switch it never read.
    expect(screen.queryByText("Clear")).toBeNull();
  });

  it("an autonomy body that does not report the poller is not a read of it", async () => {
    serve([], { autonomy: { poll_count: 3 } });
    const text = await needsText();
    expect(text).not.toMatch(ALL_CLEAR);
    expect(text).toMatch(NEED_FOR.autonomy);
  });

  it("failed Linear queue section", async () => {
    serve([], { live: { ...LIVE_GOOD, queue: { available: false, error: "Linear rate limited", urgent: null, high: null } } });
    const text = await needsText();
    expect(text).not.toMatch(ALL_CLEAR);
    expect(text).toMatch(/Linear queue unavailable — Linear rate limited/);
  });

  it.each(["active_sessions", "recent_completions", "hourly"])("failed session-store read (%s)", async (field) => {
    const live = field === "hourly" ? { ...LIVE_GOOD, throughput: { hourly: null } } : { ...LIVE_GOOD, [field]: null };
    serve([], { live });
    const text = await needsText();
    expect(text).not.toMatch(ALL_CLEAR);
    expect(text).toMatch(/Session store unavailable — running work is unknown/);
  });

  it("observability section missing", async () => {
    serve([], { live: { ...LIVE_GOOD, observability: undefined } });
    const text = await needsText();
    expect(text).not.toMatch(ALL_CLEAR);
    expect(text).toMatch(/Observability unavailable — component alerts unknown/);
  });

  it("queue and session store both failed (round 2 probe)", async () => {
    serve([], { live: { ...LIVE_GOOD, throughput: { hourly: null }, active_sessions: null, recent_completions: null,
      queue: { available: false, error: "Linear rate limited", urgent: null, high: null } } });
    const text = await needsText();
    expect(text).not.toMatch(ALL_CLEAR);
    expect(text).toMatch(/Linear queue unavailable — Linear rate limited/);
    expect(text).toMatch(/Session store unavailable — running work is unknown/);
  });
});

// Built lazily so the page-level cases above still run (and go red) on a
// loop-needs.ts that predates NEEDS_SOURCES; "names every source" pins the list.
const SOURCES = [...(NEEDS_SOURCES ?? [])];
const allOk = () => Object.fromEntries(SOURCES.map((s) => [s, null])) as NeedsAvailability;

describe("deriveNeeds — one availability entry per source", () => {
  it("names every source the panel reads", () => {
    expect([...SOURCES].sort()).toEqual(
      ["autonomy", "live", "observability", "queue", "routines", "sessionStore", "swarm"],
    );
  });

  it("adds nothing when every read succeeded", () => {
    expect(deriveNeeds({ availability: allOk() })).toEqual([]);
  });

  it.each(SOURCES)("%s unavailable alone adds exactly one error-level need", (source) => {
    const needs = deriveNeeds({ availability: { ...allOk(), [source]: "read failed" } });
    expect(needs).toHaveLength(1);
    expect(needs[0].color).toBe("var(--error)");
    expect(needs[0].text).toMatch(/unavailable/);
  });

  it.each(SOURCES)("%s left out of the record fails closed", (source) => {
    const partial: Partial<NeedsAvailability> = { ...allOk() };
    delete partial[source];
    const needs = deriveNeeds({ availability: partial as NeedsAvailability });
    expect(needs.length).toBeGreaterThan(0);
  });

  it("does not read swarm or autonomy flags when that read is unavailable", () => {
    const needs = deriveNeeds({
      availability: { ...allOk(), swarm: "read failed", autonomy: "read failed" },
      swarm: { kill_switch_active: false, escalation_lock_active: false },
      autonomy: { enabled: true, stale: false, poller_iteration_errors: 0, last_iteration_error: null },
    });
    expect(needs.map((n) => n.text)).toEqual([
      "Autonomy status unavailable — poller state unknown",
      "Swarm status unavailable — kill-switch state unknown",
    ]);
  });
});
