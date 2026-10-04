/**
 * RA-7898 T1 (part 2) — kill switch, provider usage, wiki graph, curator and
 * the Pi-CEO proxy feeds, each failure shape read to the right state.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  readCurator, readKillSwitch, readProviderUsage, readWikiGraph, SIGNED_OUT_REASON,
} from "@/lib/boards/sources/feeds-direct";
import { readMissionControlLive, PROXY_FEEDS } from "@/lib/boards/sources/feeds-proxy";
import { fail, KILL_SWITCH, MC_LIVE, serve, signal, without } from "./boards-feed-fixtures";

afterEach(() => vi.unstubAllGlobals());

describe("kill-switch", () => {
  it("200 without error is live", async () => { serve(KILL_SWITCH); expect((await readKillSwitch(signal)).kind).toBe("live"); });
  it("200 that is not JSON is unreachable, never live {}", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("not json", { status: 200 })));
    const r = await readKillSwitch(signal);
    expect([r.kind, r.value]).toEqual(["unreachable", { error: "invalid kill-switch status payload" }]);
  });
  it("500 with an empty body carries an error, so the panel shows UNKNOWN", async () => {
    serve({}, 500);
    const r = await readKillSwitch(signal);
    expect([r.kind, r.value.error]).toEqual(["unreachable", "HTTP 500"]);
  });
  it("200 missing the flags is unreachable", async () => { serve({}); expect((await readKillSwitch(signal)).kind).toBe("unreachable"); });
  it.each(Object.keys(KILL_SWITCH))("200 without %s is unreachable", async (key) => {
    serve(without(KILL_SWITCH, key));
    expect((await readKillSwitch(signal)).kind).toBe("unreachable");
  });
  it("approver lists must hold names", async () => {
    serve({ ...KILL_SWITCH, approver_allowlist: [{}] });
    expect((await readKillSwitch(signal)).kind).toBe("unreachable");
  });
  it("401 is unreachable with the signed-out reason", async () => {
    serve({ error: "Unauthorised" }, 401);
    const r = await readKillSwitch(signal);
    expect([r.kind, r.reason, r.httpStatus]).toEqual(["unreachable", SIGNED_OUT_REASON, 401]);
  });
  it("quiet failure is unreachable", async () => { serve({ error: "upstream unreachable" }); expect((await readKillSwitch(signal)).kind).toBe("unreachable"); });
  it("not configured is no_source", async () => {
    serve({ error: "PI_CEO_URL / RAILWAY_URL not configured" });
    expect((await readKillSwitch(signal)).kind).toBe("no_source");
  });
  it("network error keeps String(exc), as the panel showed", async () => {
    fail(); expect((await readKillSwitch(signal)).value).toEqual({ error: "Error: network down" });
  });
});

const USAGE = {
  source: "cc:provider-usage", generatedAt: "2026-10-03T00:00:00Z",
  summary: { total: 1, available: 1, watching: 0, nearLimit: 0, blocked: 0, unknown: 0 },
  providers: [{ id: "claude", label: "Claude", planType: "Max", resetCadence: "5h", state: "available", truthLevel: "estimated",
    bestUseLane: "build", fallbackProvider: null, missingSetupReason: null, usagePct: 0.2, lastChecked: "2026-10-03T00:00:00Z" }],
  routing: [{ lane: "build", recommended: "claude", reason: "primary" }],
};

describe("provider-usage", () => {
  it.each([["summary", without(USAGE, "summary")], ["routing", without(USAGE, "routing")],
    ["summary.total", { ...USAGE, summary: without(USAGE.summary, "total") }],
    ["a provider label", { ...USAGE, providers: [without(USAGE.providers[0], "label")] }],
    ["a provider usagePct", { ...USAGE, providers: [{ ...USAGE.providers[0], usagePct: "20%" }] }],
    ["a routing reason", { ...USAGE, routing: [without(USAGE.routing[0], "reason")] }],
  ])("a 200 missing or mistyping %s is unreachable", async (_k, body) => {
    serve(body);
    expect((await readProviderUsage(signal)).kind).toBe("unreachable");
  });
  it("200 is live with generatedAt", async () => {
    serve(USAGE);
    const r = await readProviderUsage(signal);
    expect([r.kind, r.serverTs]).toEqual(["live", "2026-10-03T00:00:00Z"]);
  });
  it("500 is unreachable", async () => { serve({ error: "Failed to build provider usage" }, 500); expect((await readProviderUsage(signal)).kind).toBe("unreachable"); });
});

describe("wiki-graph", () => {
  it("a sourced graph is live", async () => {
    serve({ pageCount: 3, edgeCount: 2, lastSync: null, source: "supabase" });
    expect((await readWikiGraph(signal)).kind).toBe("live");
  });
  it("source unconfigured is no_source", async () => {
    serve({ nodes: [], edges: [], pageCount: 0, edgeCount: 0, lastSync: null, source: "unconfigured", reason: "no key" });
    const r = await readWikiGraph(signal);
    expect([r.kind, r.reason]).toEqual(["no_source", "no key"]);
  });
  it("non-200 is unreachable", async () => { serve({}, 500); expect((await readWikiGraph(signal)).kind).toBe("unreachable"); });
  it.each([
    ["pageCount", { edgeCount: 2, source: "supabase" }],
    ["edgeCount", { pageCount: 3, source: "supabase" }],
    ["source", { pageCount: 3, edgeCount: 2 }],
  ])("a 200 without %s is unreachable", async (_f, body) => {
    serve(body);
    expect((await readWikiGraph(signal)).kind).toBe("unreachable");
  });
  it("a 200 {} is unreachable, never zero pages shown as live", async () => {
    serve({});
    expect((await readWikiGraph(signal)).kind).toBe("unreachable");
  });
});

const CUR_ROW = { ts: "2026-10-04T00:00:00Z", proposal_id: "p1", status: "pending" };
const curList = (row: Record<string, unknown>) => ({ total: 1, returned: 1, by_status: { pending: 1 }, proposals: [row] });

describe("curator", () => {
  it("200 without error is live", async () => { serve({ total: 0, returned: 0, proposals: [], by_status: {} }); expect((await readCurator(signal)).kind).toBe("live"); });
  it("200 without by_status is unreachable", async () => { serve(without(curList(CUR_ROW), "by_status")); expect((await readCurator(signal)).kind).toBe("unreachable"); });
  it("a non-numeric count is unreachable", async () => { serve({ ...curList(CUR_ROW), by_status: { pending: 1, accepted: "1" } }); expect((await readCurator(signal)).kind).toBe("unreachable"); });
  it("a row without ts is unreachable", async () => { serve(curList(without(CUR_ROW, "ts"))); expect((await readCurator(signal)).kind).toBe("unreachable"); });
  it("a numeric draft_id is unreachable", async () => { serve(curList({ ...CUR_ROW, draft_id: 42 })); expect((await readCurator(signal)).kind).toBe("unreachable"); });
  it("a text evidence_count is unreachable", async () => { serve(curList({ ...CUR_ROW, evidence_count: "3" })); expect((await readCurator(signal)).kind).toBe("unreachable"); });
  it("a row with an object field is unreachable", async () => { serve(curList({ ...CUR_ROW, cluster_summary: {} })); expect((await readCurator(signal)).kind).toBe("unreachable"); });
  it("200 that is not JSON is unreachable, never an empty list", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("not json", { status: 200 })));
    const r = await readCurator(signal);
    expect([r.kind, r.value]).toEqual(["unreachable", { error: "invalid curator proposals payload" }]);
  });
  it("quiet failure is unreachable", async () => { serve({ error: "upstream unreachable" }); expect((await readCurator(signal)).kind).toBe("unreachable"); });
  it("not configured is no_source", async () => {
    serve({ error: "PI_CEO_URL / RAILWAY_URL not configured" });
    expect((await readCurator(signal)).kind).toBe("no_source");
  });
});

describe("Pi-CEO proxy feeds", () => {
  it.each(PROXY_FEEDS.map((f) => [f.id, f] as const))("%s: the proxy's 200 fallback with X-Upstream-Status is unreachable", async (_id, def) => {
    serve([], 200, { "X-Upstream-Status": "502" });
    const r = await def.read(signal);
    expect([r.kind, r.value]).toEqual(["unreachable", null]);
  });
  const good: Record<string, unknown> = {
    "pi-health": { status: "ok" }, "mc-live": MC_LIVE,
    "idea-pipeline": { snapshot: { intake: "", north_star: "", awaiting: 0, packet: null, verdicts: [], go_required: true, executed: false } }, sessions: [], "projects-health": [], pipelines: [],
    "mesh-lanes": { events: [], cursor: 0 },
  };
  it.each(PROXY_FEEDS.map((f) => [f.id, f] as const))("%s: a real 200 is live and reads through /api/pi-ceo", async (_id, def) => {
    const fn = serve(good[def.id]);
    const r = await def.read(signal);
    expect(r.kind).toBe("live");
    // def.url reads "Pi-CEO <path> (proxy)"; the wire URL is the proxy prefix plus that path.
    const path = def.url.replace(/^Pi-CEO /, "").replace(/ \(proxy\)$/, "");
    expect(String(fn.mock.calls[0][0])).toBe(`/api/pi-ceo${path}`);
  });
  it.each(PROXY_FEEDS.map((f) => [f.id, f] as const))("%s: a malformed 200 is unreachable, never live", async (_id, def) => {
    serve(def.id === "sessions" || def.id === "projects-health" || def.id === "pipelines" ? {} : []);
    expect((await def.read(signal)).kind).toBe("unreachable");
    serve("not a payload");
    expect((await def.read(signal)).kind).toBe("unreachable");
  });
  it("mission-control/live: a non-text error drops the body", async () => {
    serve({ ...MC_LIVE, error: {} });
    const r = await readMissionControlLive();
    expect([r.kind, r.value]).toEqual(["unreachable", null]);
  });
  it.each(Object.keys(MC_LIVE))("mission-control/live: a 200 without %s is unreachable", async (key) => {
    serve(without(MC_LIVE, key));
    expect((await readMissionControlLive()).kind).toBe("unreachable");
  });
  it.each([["queue.urgent", { high: 0 }], ["queue.high", { urgent: 0 }]])("mission-control/live: a 200 without %s is unreachable", async (_k, queue) => {
    serve({ ...MC_LIVE, queue });
    expect((await readMissionControlLive()).kind).toBe("unreachable");
  });
  it("mission-control/live: a 200 without throughput.hourly is unreachable", async () => {
    serve({ ...MC_LIVE, throughput: {} });
    expect((await readMissionControlLive()).kind).toBe("unreachable");
  });
  it("mission-control/live: a 200 {} is unreachable", async () => {
    serve({});
    expect((await readMissionControlLive()).kind).toBe("unreachable");
  });
  it.each(PROXY_FEEDS.map((f) => [f.id, f] as const))("%s: the poller's abort signal reaches fetch", async (_id, def) => {
    const fn = serve(good[def.id]);
    const controller = new AbortController();
    await def.read(controller.signal);
    expect((fn.mock.calls[0] as unknown[])[1]).toMatchObject({ signal: controller.signal });
  });
  it("mission-control/live: a body error is unreachable; ts is the server clock", async () => {
    serve({ ...MC_LIVE, error: "boom" });
    expect((await readMissionControlLive()).kind).toBe("unreachable");
    serve(MC_LIVE);
    expect((await readMissionControlLive()).serverTs).toBe("2026-10-03T00:00:00Z");
  });
});
