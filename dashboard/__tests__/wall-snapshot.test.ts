/**
 * Live Wall snapshot rules (docs/briefs/live-wall-v1.md). Each case is a way the wall
 * could show false health; every one must come out GREY, never GREEN.
 */
import { describe, expect, it } from "vitest";

import { anyAbsent, isAbsent } from "@/lib/wall/absent";
import { bannerCounts, buildSnapshot, fleetPanel, machineTile, stations } from "@/lib/wall/snapshot";

const NOW = Date.parse("2026-09-19T00:00:00Z");
const ago = (s: number) => new Date(NOW - s * 1000).toISOString();
const HOSTS = ["A", "B", "C"];

describe("absent", () => {
  it.each([undefined, null, "", "   ", [], {}, Number.NaN])("%j is absent", (v) => {
    expect(isAbsent(v)).toBe(true);
  });
  it("0 is absent only for identifier/timestamp fields", () => {
    expect(isAbsent(0)).toBe(false);
    expect(isAbsent(0, { zeroIsAbsent: true })).toBe(true);
    expect(anyAbsent({ sha: "abc", first_commit: 0 })).toBe("first_commit");
  });
  it("present values are present (positive control)", () => {
    expect(anyAbsent({ sha: "abc", n: 3, list: [1], obj: { a: 1 } })).toBeNull();
  });
});

describe("machine tiles", () => {
  it("fresh heartbeat is GREEN (positive control)", () => {
    expect(machineTile("A", { host: "A", last_seen: ago(20) }, [], NOW).chip).toBe("GREEN");
  });
  it("61s-old heartbeat is GREY no signal", () => {
    const t = machineTile("A", { host: "A", last_seen: ago(61) }, [], NOW);
    expect([t.chip, t.reason, t.ageSeconds]).toEqual(["GREY", "no signal", 61]);
  });
  it.each([undefined, "", "not-a-date"])("last_seen %j is GREY, never green", (ls) => {
    expect(machineTile("A", { host: "A", last_seen: ls }, [], NOW).chip).toBe("GREY");
  });
  it("ignores upstream is_stale=false when last_seen is old", () => {
    expect(machineTile("A", { host: "A", last_seen: ago(3600), is_stale: false }, [], NOW).chip).toBe("GREY");
  });
  it("a crashed agent on a live machine goes GREY on its own clock", () => {
    const agents = [{ machine: "A", runtime: "claude", state: "working", updated_at: ago(91) }];
    const t = machineTile("A", { host: "A", last_seen: ago(5) }, agents, NOW);
    expect(t.chip).toBe("GREEN");
    expect(t.agents[0].chip).toBe("GREY");
  });
});

describe("fleet panel", () => {
  it("a failed read is broken, never an empty fleet", () => {
    const p = fleetPanel(null, HOSTS, NOW, { kind: "broken", reason: "SOURCE BROKEN — x" });
    expect(p.status).toBe("broken");
    expect(p.machines.map((m) => m.chip)).toEqual(["GREY", "GREY", "GREY"]);
  });
  it("malformed body and machines-source error are broken", () => {
    expect(fleetPanel({}, HOSTS, NOW).status).toBe("broken");
    expect(fleetPanel({ machines: [], errors: [{ source: "machines" }] }, HOSTS, NOW).status).toBe("broken");
  });
  it("a declared host that never reported is GREY; strangers are listed, not counted", () => {
    const p = fleetPanel({ machines: [{ host: "A", last_seen: ago(1) }, { host: "ghost", last_seen: ago(1) }] }, HOSTS, NOW);
    expect(p.machines.map((m) => m.chip)).toEqual(["GREEN", "GREY", "GREY"]);
    expect(p.others).toEqual(["ghost"]);
  });
});

describe("stations and banner", () => {
  it("every station starts GREY with the source it needs", () => {
    const st = stations();
    expect(st).toHaveLength(7);
    expect(st.every((s) => s.chip === "GREY" && s.reason.startsWith("NO LIVE SOURCE YET — needs "))).toBe(true);
  });
  it("banner counts every chip and renders zeros as numbers", () => {
    const p = fleetPanel({ machines: HOSTS.map((h) => ({ host: h, last_seen: ago(1) })) }, HOSTS, NOW);
    expect(bannerCounts(p, [])).toEqual({ red: 0, grey: 0 });
    expect(bannerCounts(p, stations())).toEqual({ red: 0, grey: 7 });
  });
  it("snapshot is stamped with its build time", () => {
    const snap = buildSnapshot(fleetPanel(null, HOSTS, NOW, { kind: "no_source", reason: "r" }), NOW);
    expect(snap.generated_at).toBe("2026-09-19T00:00:00.000Z");
    expect(snap.banner).toEqual({ red: 0, grey: 10 });
  });
});
