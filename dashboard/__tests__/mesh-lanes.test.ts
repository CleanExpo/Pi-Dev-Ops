/**
 * Claude lanes — projection, BFF route and board feed reader.
 *
 * What this pins:
 *   1. A failed or malformed read is `unavailable`, never an empty lane list.
 *   2. Cost a lane did not report stays null (shown "unknown"), never 0.
 *   3. The BFF never echoes the secret it attaches upstream.
 *   4. The feed reader maps "not configured" to no_source and everything else to unreachable.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { projectLanes } from "@/lib/control/mesh-lanes";
import { readMeshLanes } from "@/lib/boards/sources/feeds-direct";

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

describe("GET /api/mesh-fleet/lanes", () => {
  const SECRET = "mesh-lanes-test-secret";
  const saved: Record<string, string | undefined> = {};
  const ENV = ["TAO_FLEET_READ_SECRET", "TAO_INTERNAL_WEBHOOK_SECRET", "TAO_WEBHOOK_SECRET", "RAILWAY_URL", "PI_CEO_URL"] as const;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    for (const key of ENV) { saved[key] = process.env[key]; delete process.env[key]; }
    process.env.PI_CEO_URL = "http://pi-ceo.test";
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    for (const key of ENV) {
      if (saved[key] === undefined) delete process.env[key];
      else process.env[key] = saved[key];
    }
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("is unavailable without a secret and never calls upstream", async () => {
    const { GET } = await import("../app/api/mesh-fleet/lanes/route");
    const res = await GET();
    expect(res.status).toBe(503);
    expect(await res.json()).toMatchObject({ status: "unavailable", reason: "mesh secret not configured" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("is unavailable when upstream answers 502 (table not applied yet)", async () => {
    process.env.TAO_FLEET_READ_SECRET = SECRET;
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: "lane-events read failed (404)" }), { status: 502 }));
    const { GET } = await import("../app/api/mesh-fleet/lanes/route");
    const res = await GET();
    expect(res.status).toBe(503);
    expect((await res.json()).reason).toBe("upstream unreachable");
  });

  it("projects lanes, asks for the newest events, and never echoes the secret", async () => {
    process.env.TAO_FLEET_READ_SECRET = SECRET;
    fetchMock.mockResolvedValue(new Response(JSON.stringify(EVENTS), { status: 200, headers: { "content-type": "application/json" } }));
    const { GET } = await import("../app/api/mesh-fleet/lanes/route");
    const res = await GET();
    expect(res.status).toBe(200);
    const text = await res.text();
    expect(text).not.toContain(SECRET);
    const body = JSON.parse(text);
    expect(body.status).toBe("ok");
    expect(body.lanes).toHaveLength(2);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://pi-ceo.test/api/mesh/lane-events?newest=true&limit=500");
    expect((init as RequestInit).headers).toEqual({ "X-Pi-CEO-Secret": SECRET });
  });
});

describe("readMeshLanes (board feed)", () => {
  afterEach(() => vi.unstubAllGlobals());

  function answer(status: number, body: unknown) {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status })));
  }

  it("live on an ok body", async () => {
    answer(200, projectLanes(EVENTS, CHECKED));
    const r = await readMeshLanes(new AbortController().signal);
    expect(r.kind).toBe("live");
    expect(r.serverTs).toBe(CHECKED);
  });

  it("no_source when the BFF says the secret or URL is not configured", async () => {
    answer(503, { status: "unavailable", checkedAt: CHECKED, reason: "mesh secret not configured" });
    expect((await readMeshLanes(new AbortController().signal)).kind).toBe("no_source");
  });

  it("unreachable when upstream failed, with the reason", async () => {
    answer(503, { status: "unavailable", checkedAt: CHECKED, reason: "upstream unreachable" });
    const r = await readMeshLanes(new AbortController().signal);
    expect(r.kind).toBe("unreachable");
    expect(r.reason).toBe("upstream unreachable");
  });

  it("unreachable, not live, for a 200 whose lanes are not a list", async () => {
    answer(200, { status: "ok", checkedAt: CHECKED, windowEvents: 0, lanes: "x" });
    expect((await readMeshLanes(new AbortController().signal)).kind).toBe("unreachable");
  });
});
