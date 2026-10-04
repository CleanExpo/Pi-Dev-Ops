/**
 * RA-7898 T1 — one reader per feed, each failure shape from
 * docs/specs/modular-boards.md §3.3 read to the right state.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  readCurator, readKillSwitch, readMeshFleet, readModelFabric, readProviderUsage, readSwarmStatus,
  readWall, readWikiGraph, SIGNED_OUT_REASON,
} from "@/lib/boards/sources/feeds-direct";
import { readMissionControlLive, PROXY_FEEDS } from "@/lib/boards/sources/feeds-proxy";

const signal = new AbortController().signal;

function serve(body: unknown, status = 200, headers: Record<string, string> = {}) {
  const fn = vi.fn(async (_url: string) => new Response(JSON.stringify(body), { status, headers }));
  vi.stubGlobal("fetch", fn);
  return fn;
}
function fail(message = "network down") {
  vi.stubGlobal("fetch", vi.fn(async () => { throw new Error(message); }));
}

afterEach(() => vi.unstubAllGlobals());

describe("mesh-fleet", () => {
  it("unavailable with a non-text reason is the fallback value", async () => {
    serve({ status: "unavailable", checkedAt: "2026-10-04T00:00:00Z", reason: {} }, 503);
    const r = await readMeshFleet(signal);
    expect([r.kind, r.value.status, typeof (r.value as { reason: unknown }).reason]).toEqual(["unreachable", "unavailable", "string"]);
  });
  it("a 503 with an ok-shaped body is the unavailable value, never a fleet", async () => {
    serve({ status: "ok", checkedAt: "2026-10-04T00:00:00Z", machines: [] }, 503);
    const r = await readMeshFleet(signal);
    expect([r.kind, r.value.status]).toEqual(["unreachable", "unavailable"]);
  });
  it("a 200 ok without checkedAt is unreachable", async () => {
    serve({ status: "ok", machines: [] });
    expect((await readMeshFleet(signal)).kind).toBe("unreachable");
  });
  it("a 200 ok without a machine list is unreachable", async () => {
    serve({ status: "ok", checkedAt: "2026-10-03T00:00:00Z" });
    const r = await readMeshFleet(signal);
    expect([r.kind, r.value.status]).toEqual(["unreachable", "unavailable"]);
  });
  it("200 ok is live with checkedAt as the server clock", async () => {
    serve({ status: "ok", checkedAt: "2026-10-03T00:00:00Z", machines: [] });
    const r = await readMeshFleet(signal);
    expect(r.kind).toBe("live");
    expect(r.serverTs).toBe("2026-10-03T00:00:00Z");
  });
  it.each(["upstream unreachable", "fleet snapshot missing", "machines source failed"])("503 %s is unreachable", async (reason) => {
    serve({ status: "unavailable", checkedAt: "x", reason }, 503);
    const r = await readMeshFleet(signal);
    expect([r.kind, r.reason]).toEqual(["unreachable", reason]);
  });
  it.each(["mesh secret not configured", "Pi-CEO URL not configured"])("503 %s is no_source", async (reason) => {
    serve({ status: "unavailable", checkedAt: "x", reason }, 503);
    expect((await readMeshFleet(signal)).kind).toBe("no_source");
  });
  it("a network error is unreachable with the panel's own fallback value", async () => {
    fail();
    const r = await readMeshFleet(signal);
    expect(r.kind).toBe("unreachable");
    expect(r.value).toMatchObject({ status: "unavailable", reason: "fleet read failed" });
  });
});

describe("wall", () => {
  const snap = (status: string) => ({ generated_at: "2026-10-03T00:00:00Z", banner: { red: 0, grey: 0 },
    fleet: { status, reason: status === "ok" ? "" : "why", machines: [], others: [] }, stations: [] });
  it("fleet ok is live with generated_at", async () => {
    serve(snap("ok"));
    const r = await readWall(signal);
    expect([r.kind, r.serverTs]).toEqual(["live", "2026-10-03T00:00:00Z"]);
  });
  it("fleet ok without generated_at is unreachable", async () => {
    serve({ fleet: { status: "ok", reason: "", machines: [], others: [] }, stations: [], banner: { red: 0, grey: 0 } });
    expect((await readWall(signal)).kind).toBe("unreachable");
  });
  it("fleet ok without a machine list is unreachable", async () => {
    serve({ generated_at: "2026-10-03T00:00:00Z", fleet: { status: "ok", reason: "", others: [] }, stations: [], banner: { red: 0, grey: 0 } });
    expect((await readWall(signal)).kind).toBe("unreachable");
  });
  it("fleet broken with a non-text reason drops the body", async () => {
    serve({ generated_at: "2026-10-03T00:00:00Z", fleet: { status: "broken", reason: {}, machines: [], others: [] }, stations: [], banner: { red: 0, grey: 0 } });
    const r = await readWall(signal);
    expect([r.kind, r.value]).toEqual(["unreachable", null]);
  });
  it("fleet broken is unreachable", async () => { serve(snap("broken")); expect((await readWall(signal)).kind).toBe("unreachable"); });
  it("fleet no_source is no_source", async () => { serve(snap("no_source")); expect((await readWall(signal)).kind).toBe("no_source"); });
  it("non-200 and network are unreachable", async () => {
    serve({}, 500); expect((await readWall(signal)).kind).toBe("unreachable");
    fail(); expect((await readWall(signal)).kind).toBe("unreachable");
  });
});

describe("model-fabric", () => {
  it("200 is live", async () => { serve({ enabled: true, healthy: true }); expect((await readModelFabric(signal)).kind).toBe("live"); });
  it("503 is unreachable and keeps the route's error", async () => {
    serve({ enabled: false, healthy: false, error: "Pi-CEO unavailable" }, 503);
    const r = await readModelFabric(signal);
    expect([r.kind, r.reason]).toEqual(["unreachable", "Pi-CEO unavailable"]);
  });
  it("non-2xx without error gets HTTP n, as the panel did", async () => {
    serve({ enabled: true, healthy: true }, 502);
    expect((await readModelFabric(signal)).value.error).toBe("HTTP 502");
  });
  it("network error is unreachable", async () => { fail(); expect((await readModelFabric(signal)).kind).toBe("unreachable"); });
  it.each([["enabled", { healthy: true }], ["healthy", { enabled: true }]])("200 without %s is unreachable", async (_f, body) => {
    serve(body);
    expect((await readModelFabric(signal)).kind).toBe("unreachable");
  });
  it("200 without the flags is unreachable, never DISABLED", async () => {
    serve({});
    const r = await readModelFabric(signal);
    expect([r.kind, r.value.error]).toEqual(["unreachable", "invalid model-fabric status payload"]);
  });
});

describe("swarm-status", () => {
  it("a known state is live", async () => { serve({ state: "ACTIVE" }); expect((await readSwarmStatus(signal)).kind).toBe("live"); });
  it("200 without a known state is unreachable, never zeroed counters", async () => {
    serve({});
    expect((await readSwarmStatus(signal)).value).toEqual({ data: null, error: "invalid swarm status payload" });
  });
  it("the route's 200 UNKNOWN fallback is unreachable", async () => {
    serve({ state: "UNKNOWN", autonomous_prs_today: null });
    expect((await readSwarmStatus(signal)).kind).toBe("unreachable");
  });
  it("non-200 nulls data with HTTP n, as the panel did", async () => {
    serve({}, 500);
    expect((await readSwarmStatus(signal)).value).toEqual({ data: null, error: "HTTP 500" });
  });
  it("network error carries the exception message", async () => {
    fail("timeout");
    expect((await readSwarmStatus(signal)).value).toEqual({ data: null, error: "timeout" });
  });
});

describe("kill-switch", () => {
  it("200 without error is live", async () => { serve({ kill_switch_active: false, swarm_enabled_env: true }); expect((await readKillSwitch(signal)).kind).toBe("live"); });
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
  it.each([["kill_switch_active", { swarm_enabled_env: true }], ["swarm_enabled_env", { kill_switch_active: false }]])("200 without %s is unreachable", async (_f, body) => {
    serve(body);
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

describe("provider-usage", () => {
  it("200 is live with generatedAt", async () => {
    serve({ source: "cc:provider-usage", generatedAt: "2026-10-03T00:00:00Z", summary: {}, providers: [], routing: [] });
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

describe("curator", () => {
  it("200 without error is live", async () => { serve({ proposals: [], by_status: {} }); expect((await readCurator(signal)).kind).toBe("live"); });
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
    "pi-health": { status: "ok" }, "mc-live": { ts: "2026-10-03T00:00:00Z" },
    "idea-pipeline": { snapshot: {} }, sessions: [], "projects-health": [], pipelines: [],
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
    serve({ error: {}, ts: "2026-10-03T00:00:00Z" });
    const r = await readMissionControlLive();
    expect([r.kind, r.value]).toEqual(["unreachable", null]);
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
    serve({ error: "boom", ts: "2026-10-03T00:00:00Z" });
    expect((await readMissionControlLive()).kind).toBe("unreachable");
    serve({ ts: "2026-10-03T00:00:00Z" });
    expect((await readMissionControlLive()).serverTs).toBe("2026-10-03T00:00:00Z");
  });
});
