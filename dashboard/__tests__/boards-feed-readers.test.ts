/**
 * RA-7898 T1 — one reader per feed, each failure shape from
 * docs/specs/modular-boards.md §3.3 read to the right state. Fleet, wall,
 * model fabric and swarm; the rest are in boards-feed-readers-status.test.ts.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { readMeshFleet, readModelFabric, readSwarmStatus, readWall } from "@/lib/boards/sources/feeds-direct";
import { FABRIC, fail, serve, signal, SWARM, without } from "./boards-feed-fixtures";

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
  it.each([["no host", { stale: false, revision: null, lastHeartbeat: null, currentClaim: null }],
    ["an object claim", { host: "mini", stale: false, revision: null, lastHeartbeat: null, currentClaim: {} }]])("a machine row with %s is unreachable", async (_k, row) => {
    serve({ status: "ok", checkedAt: "2026-10-04T00:00:00Z", machines: [row] });
    expect((await readMeshFleet(signal)).kind).toBe("unreachable");
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
  const TILE = { host: "mini", chip: "GREEN", reason: "ok", ageSeconds: 3, load1: 0.5, selfReported: true,
    agents: [{ runtime: "claude", state: "idle", chip: "GREEN", ageSeconds: 3 }] };
  const wallWith = (machine: unknown, extra: Record<string, unknown> = {}) => ({ ...snap("ok"),
    fleet: { status: "ok", reason: "", machines: [machine], others: [] }, ...extra });
  it("a complete wall machine is live", async () => { serve(wallWith(TILE)); expect((await readWall(signal)).kind).toBe("live"); });
  it.each(["host", "chip", "reason", "ageSeconds", "load1", "agents"])("a wall machine without %s is unreachable", async (key) => {
    serve(wallWith(without(TILE, key)));
    expect((await readWall(signal)).kind).toBe("unreachable");
  });
  it.each(["runtime", "state", "chip", "ageSeconds"])("an agent without %s is unreachable", async (key) => {
    serve(wallWith({ ...TILE, agents: [without(TILE.agents[0], key)] }));
    expect((await readWall(signal)).kind).toBe("unreachable");
  });
  it("fleet others that is not a list of names is unreachable", async () => {
    serve({ ...snap("ok"), fleet: { status: "ok", reason: "", machines: [], others: "x" } });
    expect((await readWall(signal)).kind).toBe("unreachable");
  });
  it("a wall without banner counts is unreachable", async () => {
    serve({ ...snap("ok"), banner: { red: 0 } });
    expect((await readWall(signal)).kind).toBe("unreachable");
  });
  it("a station without a name is unreachable", async () => {
    serve({ generated_at: "2026-10-03T00:00:00Z", fleet: { status: "ok", reason: "", machines: [], others: [] }, stations: [{ id: "s", chip: "GREEN", reason: "" }], banner: { red: 0, grey: 0 } });
    expect((await readWall(signal)).kind).toBe("unreachable");
  });
  it("a wall machine without a chip is unreachable", async () => {
    serve({ generated_at: "2026-10-03T00:00:00Z", fleet: { status: "ok", reason: "", machines: [{ host: "mini", reason: "", agents: [] }], others: [] }, stations: [], banner: { red: 0, grey: 0 } });
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
  it("200 is live", async () => { serve(FABRIC); expect((await readModelFabric(signal)).kind).toBe("live"); });
  it.each(Object.keys(FABRIC))("200 without %s is unreachable", async (key) => {
    serve(without(FABRIC, key));
    expect((await readModelFabric(signal)).kind).toBe("unreachable");
  });
  it("a null lane is unreachable", async () => { serve({ ...FABRIC, lanes: { review: null } }); expect((await readModelFabric(signal)).kind).toBe("unreachable"); });
  it.each([["model", { banned: false }], ["banned", { model: "m" }]])("a lane without %s is unreachable", async (_k, lane) => {
    serve({ ...FABRIC, lanes: { review: lane } });
    expect((await readModelFabric(signal)).kind).toBe("unreachable");
  });
  it("a complete last call is live; a partial one is unreachable", async () => {
    const call = { ts: 1, role: "r", lane: "l", requested_model: "a", served_model: "b", provider: "p", latency_ms: 5, ok: true, attempts: ["a"] };
    serve({ ...FABRIC, last_call: call });
    expect((await readModelFabric(signal)).kind).toBe("live");
    serve({ ...FABRIC, last_call: without(call, "attempts") });
    expect((await readModelFabric(signal)).kind).toBe("unreachable");
  });
  it("blocked that is not a list of names is unreachable", async () => { serve({ ...FABRIC, blocked: [1] }); expect((await readModelFabric(signal)).kind).toBe("unreachable"); });
  it.each(Object.keys(FABRIC.totals))("200 without totals.%s is unreachable", async (key) => {
    serve({ ...FABRIC, totals: without(FABRIC.totals, key) });
    expect((await readModelFabric(signal)).kind).toBe("unreachable");
  });
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
  it("a known state is live", async () => { serve(SWARM); expect((await readSwarmStatus(signal)).kind).toBe("live"); });
  it.each(Object.keys(SWARM))("200 without %s is unreachable", async (key) => {
    serve(without(SWARM, key));
    expect((await readSwarmStatus(signal)).kind).toBe("unreachable");
  });
  it.each([["a negative count", { autonomous_prs_today: -1 }], ["a text count", { green_merges: "4" }], ["a numeric url", { last_pr_url: 5 }]])("200 with %s is unreachable", async (_k, patch) => {
    serve({ ...SWARM, ...patch });
    expect((await readSwarmStatus(signal)).kind).toBe("unreachable");
  });
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
