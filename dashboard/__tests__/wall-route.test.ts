/**
 * GET /api/mesh-fleet/wall — the snapshot route must never turn a missing credential
 * or a failed upstream into a healthy-looking or empty fleet, and must stay behind
 * the dashboard session.
 */
import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { proxy } from "../proxy";
import { _resetWallCache } from "@/lib/wall/source";

const ENV = ["TAO_INTERNAL_WEBHOOK_SECRET", "TAO_WEBHOOK_SECRET", "RAILWAY_URL", "PI_CEO_URL", "WALL_FLEET_HOSTS"];
const saved: Record<string, string | undefined> = {};

async function get() {
  const { GET } = await import("@/app/api/mesh-fleet/wall/route");
  return (await (await GET()).json()) as { fleet: { status: string; reason: string; machines: { chip: string }[] }; generated_at: string };
}

beforeEach(() => {
  for (const k of ENV) { saved[k] = process.env[k]; delete process.env[k]; }
  process.env.WALL_FLEET_HOSTS = "A,B";
  _resetWallCache();
});
afterEach(() => {
  for (const k of ENV) { if (saved[k] === undefined) delete process.env[k]; else process.env[k] = saved[k]; }
  vi.unstubAllGlobals();
});

describe("wall snapshot route", () => {
  it("no secret -> NO LIVE SOURCE, every machine GREY", async () => {
    const body = await get();
    expect(body.fleet.status).toBe("no_source");
    expect(body.fleet.reason).toContain("NO LIVE SOURCE YET");
    expect(body.fleet.machines.map((m) => m.chip)).toEqual(["GREY", "GREY"]);
  });

  it("upstream failure -> SOURCE BROKEN, not an empty fleet", async () => {
    process.env.TAO_WEBHOOK_SECRET = "s";
    process.env.RAILWAY_URL = "https://pi.invalid";
    vi.stubGlobal("fetch", vi.fn(async () => new Response("no", { status: 401 })));
    const body = await get();
    expect(body.fleet.status).toBe("broken");
    expect(body.fleet.machines).toHaveLength(2);
  });

  it("live upstream -> fresh host GREEN, silent host GREY (positive control)", async () => {
    process.env.TAO_WEBHOOK_SECRET = "s";
    process.env.RAILWAY_URL = "https://pi.invalid";
    const fleet = { machines: [{ host: "A", last_seen: new Date().toISOString() }], agents: [] };
    const fetchMock = vi.fn(async () => Response.json(fleet));
    vi.stubGlobal("fetch", fetchMock);
    const body = await get();
    expect(body.fleet.status).toBe("ok");
    expect(body.fleet.machines.map((m) => m.chip)).toEqual(["GREEN", "GREY"]);
    const headers = (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].headers as Record<string, string>;
    expect(headers["X-Pi-CEO-Secret"]).toBe("s");
  });

  it("is refused without a dashboard session", async () => {
    const res = await proxy(new NextRequest(new URL("/api/mesh-fleet/wall", "https://pi.invalid")));
    expect(res.status).toBe(401);
  });
});
