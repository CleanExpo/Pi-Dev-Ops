/**
 * /control command wall derivations. A failed read is never a zero, a missing
 * source is never an all-clear, and unbuilt hops are never "connected".
 */
import { describe, expect, it } from "vitest";
import {
  CAMPAIGN_HOPS, ageText, deriveAlerts, fleetTiles, hostLabel, prRow, type RepoBoard,
} from "@/lib/control/command-wall";
import { parseRepoBoard } from "@/lib/control/useRepoBoards";
import { buildSnapshot, fleetPanel } from "@/lib/wall/snapshot";

const NOW = Date.parse("2026-11-04T08:00:00Z");
const iso = (secondsAgo: number) => new Date(NOW - secondsAgo * 1000).toISOString();

function row(id: string) {
  return { id, title: id, url: "#", lane: "engineer" as const, column: "audit" as const, ageDays: 1, tone: "ok" as const, receipts: "" };
}

function board(over: Partial<RepoBoard> = {}): RepoBoard {
  return {
    ok: true, checked_at: iso(0), error: null, awaiting_phill_long: false, repo: "CleanExpo/Synthex",
    columns: { shipped: [], audit: [row("PR-1")], phill: [row("PR-2"), row("PR-3")], aging: [] },
    pull_requests: { status: "ok", value: { count: 3, capped: false } },
    ci: { status: "ok", value: { branch: "main", sha: "abc", state: "success" } },
    ...over,
  };
}

describe("fleet tiles", () => {
  const raw = {
    machines: [
      { host: "Phills-Mac-mini", last_seen: iso(10), load1: 1.5 },
      { host: "Phills-MacBook-Pro", last_seen: iso(600) },
    ],
    agents: [{ machine: "Phills-Mac-mini", runtime: "claude", state: "busy", updated_at: iso(5) }],
  };
  const wall = buildSnapshot(fleetPanel(raw, ["Phills-MacBook-Pro", "Phills-Mac-mini", "Phill_Desktop"], NOW), NOW);

  it("names the three machines and grades heartbeat freshness", () => {
    const tiles = fleetTiles(wall, null);
    expect(tiles.map((t) => t.label)).toEqual(["MacBook", "Mac Mini", "PC"]);
    expect(tiles.map((t) => t.tone)).toEqual(["warn", "ok", "idle"]);
    expect(tiles[1].agents).toEqual([{ runtime: "claude", state: "busy", fresh: true }]);
    expect(tiles[2].status).toBe("never reported");
  });

  it("job claims are unreadable (undefined), not 'none', when the claims feed failed", () => {
    expect(fleetTiles(wall, { status: "unavailable", checkedAt: iso(0), reason: "x" })[1].claim).toBeUndefined();
    const ok = {
      status: "ok" as const, checkedAt: iso(0), claimsAvailable: true,
      machines: [{ host: "Phills-Mac-mini", revision: null, lastHeartbeat: null, currentClaim: "RA-1", stale: false, placeholder: false }],
    };
    expect(fleetTiles(wall, ok)[1].claim).toBe("RA-1");
    expect(fleetTiles(wall, ok)[0].claim).toBeNull();
  });

  it("no wall snapshot means no tiles, never three quiet machines", () => {
    expect(fleetTiles(null, null)).toEqual([]);
  });

  it("formats ages and unknown hosts plainly", () => {
    expect(ageText(null)).toBe("never");
    expect(ageText(42)).toBe("42 s");
    expect(ageText(7200)).toBe("2 h");
    expect(hostLabel("other-box")).toBe("other-box");
  });
});

describe("PR rows", () => {
  it("reads open, review, needs-Phill and aging counts from the board", () => {
    const r = prRow("CleanExpo/Synthex", board());
    expect(r).toMatchObject({ name: "Synthex", open: 3, review: 1, needsPhill: 2, aging: 0, reason: null });
    expect(r.ci).toEqual({ tone: "ok", text: "passing" });
  });

  it("a failed GitHub read is unknown (null), never zero", () => {
    const failed = board({
      ok: false, error: "GitHub unavailable: GITHUB_TOKEN not set",
      columns: { shipped: [], audit: [], phill: [], aging: [] },
      pull_requests: { status: "unavailable", reason: "GITHUB_TOKEN not set" },
      ci: { status: "unavailable", reason: "GITHUB_TOKEN not set" },
    });
    const r = prRow("CleanExpo/Synthex", failed);
    expect([r.open, r.review, r.needsPhill, r.aging]).toEqual([null, null, null, null]);
    expect(r.reason).toBe("GITHUB_TOKEN not set");
    expect(r.ci.text).toBe("unavailable");
    expect(prRow("CleanExpo/x", null, "flow board HTTP 500").reason).toBe("flow board HTTP 500");
  });

  it("parses the real /api/flow-board payload shape and rejects a malformed one", () => {
    const payload = { ...board(), columns: { shipped: [], audit: [{ ...row("PR-9"), url: "https://github.com/CleanExpo/Synthex/pull/9" }], phill: [], aging: [] } };
    expect(parseRepoBoard(JSON.parse(JSON.stringify(payload)))?.columns.audit).toHaveLength(1);
    expect(parseRepoBoard({ ok: true })).toBeNull();
  });
});

describe("alerts", () => {
  const base = { sources: [], fleet: [], prs: [] };

  it("nothing raised from nothing", () => {
    expect(deriveAlerts(base)).toEqual([]);
  });

  it("raises failed sources, kill switch, red components, urgent queue and failing CI, worst first", () => {
    const alerts = deriveAlerts({
      ...base,
      sources: [
        { id: "wall", label: "Fleet heartbeats", state: "stale", reason: null },
        { id: "mc-live", label: "Backend", state: "unreachable", reason: "Pi-CEO backend unreachable" },
      ],
      killSwitch: { kill_switch_active: true },
      observability: { red_components: ["railway"], degraded_components: ["linear"] },
      queue: { available: true, urgent: 2, high: 0 },
      prs: [prRow("CleanExpo/carsi", board({ ci: { status: "ok", value: { branch: "main", sha: "a", state: "failure" } } }))],
    });
    const text = alerts.map((a) => a.text);
    expect(text).toContain("Kill switch is ACTIVE: autonomous work is halted");
    expect(text).toContain("railway is red");
    expect(text).toContain("2 urgent ticket(s) in the queue");
    expect(text).toContain("carsi main branch CI failing");
    expect(text).toContain("Backend unreachable: Pi-CEO backend unreachable");
    expect(alerts[0].tone).toBe("bad");
    expect(alerts.at(-1)?.tone).toBe("warn");
  });

  it("an unreadable Linear queue is an alert, not a quiet queue", () => {
    expect(deriveAlerts({ ...base, queue: { available: false, error: "401" } })[0].text).toBe("Linear queue unreadable: 401");
  });
});

describe("campaign flow", () => {
  it("no hop claims to be connected until a reader exists", () => {
    expect(CAMPAIGN_HOPS.length).toBeGreaterThan(0);
    expect(CAMPAIGN_HOPS.every((h) => h.connected === false)).toBe(true);
  });
});
