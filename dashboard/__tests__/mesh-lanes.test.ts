/**
 * Claude lanes — projection and board feed reader.
 *
 * What this pins:
 *   1. A failed or malformed read is `unavailable`, never an empty lane list.
 *   2. Cost a lane did not report stays null (shown "unknown"), never 0.
 *   3. The board reads through the allowlisted, session-gated Pi-CEO proxy path —
 *      no dashboard API route (RA-7898 G2/G3) and no secret in the browser.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/pi-ceo-fetch", () => ({ fetchProxyJSON: vi.fn() }));

import { projectLanes } from "@/lib/control/mesh-lanes";
import { readMeshLanes } from "@/lib/boards/sources/feeds-proxy";
import { allowed } from "@/lib/pi-ceo-proxy-allowlist";
import { fetchProxyJSON } from "@/lib/pi-ceo-fetch";

const CHECKED = "2026-10-04T12:00:00.000Z";

const EVENTS = {
  events: [
    { id: 9, host: "Phills-Mac-mini", session_id: "a", seq: 9, kind: "usage", received_at: "2026-10-04T11:59:50Z", ctx_pct: 41, rate_pct: 12, cost_usd: 0.84 },
    { id: 8, host: "Phills-Mac-mini", session_id: "a", seq: 8, kind: "tool", received_at: "2026-10-04T11:59:40Z", tool: "Bash", ok: false },
    { id: 7, host: "Phills-Mac-mini", session_id: "a", seq: 7, kind: "tool", received_at: "2026-10-04T11:59:30Z", tool: "Read", ok: true },
    { id: 6, host: "Phills-Mac-mini", session_id: "a", seq: 6, kind: "session_start", received_at: "2026-10-04T11:50:00Z", repo: "CleanExpo/Pi-Dev-Ops", model: "claude-opus-5-5" },
    { id: 5, host: "Phill_Desktop", session_id: "b", seq: 5, kind: "session_end", received_at: "2026-10-04T11:40:00Z" },
    { id: 4, host: "Phill_Desktop", session_id: "b", seq: 4, kind: "usage", received_at: "2026-10-04T11:39:00Z", ctx_pct: 90 },
  ],
  cursor: 9,
};

describe("projectLanes", () => {
  it("folds events into one row per session, live lanes first", () => {
    const view = projectLanes(EVENTS, CHECKED);
    expect(view.status).toBe("ok");
    if (view.status !== "ok") return;
    expect(view.windowEvents).toBe(6);
    expect(view.lanes.map((l) => l.sessionId)).toEqual(["a", "b"]);
    expect(view.lanes[0]).toMatchObject({
      host: "Phills-Mac-mini", repo: "CleanExpo/Pi-Dev-Ops", model: "claude-opus-5-5", ended: false,
      toolCalls: 2, toolFails: 1, lastTool: "Bash", ctxPct: 41, ratePct: 12, costUsd: 0.84,
      lastAt: "2026-10-04T11:59:50Z",
    });
    expect(view.lanes[1].ended).toBe(true);
  });

  it("keeps an unreported cost as null, never 0", () => {
    const view = projectLanes(EVENTS, CHECKED);
    if (view.status !== "ok") throw new Error("expected ok");
    expect(view.lanes[1].costUsd).toBeNull();
    expect(view.lanes[1].ratePct).toBeNull();
  });

  it.each([null, [], { events: "nope" }, { error: "x" }])("a malformed body %j is unavailable, not empty", (raw) => {
    expect(projectLanes(raw, CHECKED).status).toBe("unavailable");
  });

  it("an empty event list is ok with no lanes (nothing reported), distinct from unavailable", () => {
    const view = projectLanes({ events: [], cursor: 0 }, CHECKED);
    expect(view).toEqual({ status: "ok", checkedAt: CHECKED, windowEvents: 0, lanes: [] });
  });
});

describe("readMeshLanes (board feed, through the Pi-CEO proxy)", () => {
  afterEach(() => vi.mocked(fetchProxyJSON).mockReset());

  it("live: folds the newest events into lanes, path is the allowlisted session-gated read", async () => {
    vi.mocked(fetchProxyJSON).mockResolvedValue(EVENTS as never);
    const r = await readMeshLanes(new AbortController().signal);
    expect(r.kind).toBe("live");
    expect(r.value?.status).toBe("ok");
    if (r.value?.status === "ok") expect(r.value.lanes).toHaveLength(2);
    expect(vi.mocked(fetchProxyJSON).mock.calls[0][0]).toBe("/api/mission-control/lane-events");
    expect(allowed("/api/mission-control/lane-events")).toBe(true);
  });

  it("unreachable, not an empty list, when the backend did not answer (proxy placeholder → null)", async () => {
    vi.mocked(fetchProxyJSON).mockResolvedValue(null);
    const r = await readMeshLanes(new AbortController().signal);
    expect(r.kind).toBe("unreachable");
    expect(r.value).toBeNull();
  });

  it("unreachable for a body whose events are not a list", async () => {
    vi.mocked(fetchProxyJSON).mockResolvedValue({ detail: "lane-events read failed (404)" } as never);
    const r = await readMeshLanes(new AbortController().signal);
    expect(r.kind).toBe("unreachable");
    expect(r.reason).toBe("invalid lane-events payload");
  });

  it("live with no lanes when nothing has reported yet (distinct from unreachable)", async () => {
    vi.mocked(fetchProxyJSON).mockResolvedValue({ events: [], cursor: 0 } as never);
    const r = await readMeshLanes(new AbortController().signal);
    expect(r.kind).toBe("live");
    if (r.value?.status === "ok") expect(r.value.lanes).toEqual([]);
  });
});
