/**
 * UNI-2649 — server-side fleet aggregate.
 *
 * Two properties this pins:
 *   1. A failed machines read is `unavailable`, never an empty enrolled list.
 *   2. The BFF never echoes the webhook secret it attaches upstream.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { projectFleet } from "@/lib/control/mesh-fleet";

const CHECKED = "2026-09-13T12:00:00.000Z";

const UPSTREAM = {
  machines: [
    {
      host: "unite-mac-mini",
      version: "mesh-runner@a1b2",
      last_seen: "2026-09-13T11:59:40.000Z",
      is_stale: false,
    },
    {
      host: "phill-desktop",
      version: "mesh-runner@c3d4",
      last_seen: "2026-09-13T11:50:00.000Z",
      is_stale: true,
    },
    {
      host: "phills-macbook",
      version: "mesh-runner@e5f6",
      last_seen: "2026-09-13T11:59:50.000Z",
      is_stale: false,
    },
  ],
  claims: [{ machine: "unite-mac-mini", linear_id: "UNI-2649", state: "working" }],
  agents: [],
  ships: [],
  degraded: false,
  errors: [],
};

describe("projectFleet", () => {
  it("maps revision, heartbeat, claim and keeps a checkedAt stamp", () => {
    const view = projectFleet(UPSTREAM, CHECKED);
    expect(view.status).toBe("ok");
    if (view.status !== "ok") return;
    expect(view.checkedAt).toBe(CHECKED);
    expect(view.machines).toEqual([
      {
        host: "unite-mac-mini",
        revision: "mesh-runner@a1b2",
        lastHeartbeat: "2026-09-13T11:59:40.000Z",
        currentClaim: "UNI-2649",
        stale: false,
      },
      {
        host: "phill-desktop",
        revision: "mesh-runner@c3d4",
        lastHeartbeat: "2026-09-13T11:50:00.000Z",
        currentClaim: null,
        stale: true,
      },
      {
        host: "phills-macbook",
        revision: "mesh-runner@e5f6",
        lastHeartbeat: "2026-09-13T11:59:50.000Z",
        currentClaim: null,
        stale: false,
      },
    ]);
  });

  it("treats a failed machines source as unavailable, not an empty fleet", () => {
    const view = projectFleet(
      { machines: [], claims: [], errors: [{ source: "machines", reason: "http-error" }] },
      CHECKED,
    );
    expect(view).toEqual({
      status: "unavailable",
      checkedAt: CHECKED,
      reason: "machines source failed",
    });
  });

  it("treats a missing or non-list machines field as unavailable", () => {
    expect(projectFleet({ error: "nope" }, CHECKED).status).toBe("unavailable");
    expect(projectFleet({ machines: { host: "x" } }, CHECKED).status).toBe("unavailable");
    expect(projectFleet(null, CHECKED).status).toBe("unavailable");
  });

  it("keeps a genuine empty enrolment distinct from unavailable", () => {
    const view = projectFleet({ machines: [], claims: [], errors: [] }, CHECKED);
    expect(view.status).toBe("ok");
    if (view.status !== "ok") return;
    expect(view.machines).toEqual([]);
  });
});

describe("GET /api/mesh-fleet", () => {
  const SECRET = "super-secret-test-value";
  const saved: Record<string, string | undefined> = {};
  const ENV = ["TAO_INTERNAL_WEBHOOK_SECRET", "TAO_WEBHOOK_SECRET", "RAILWAY_URL", "PI_CEO_URL"] as const;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    for (const key of ENV) saved[key] = process.env[key];
    delete process.env.TAO_INTERNAL_WEBHOOK_SECRET;
    delete process.env.TAO_WEBHOOK_SECRET;
    delete process.env.RAILWAY_URL;
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

  it("returns unavailable when the secret is missing — never an empty fleet", async () => {
    const { GET } = await import("../app/api/mesh-fleet/route");
    const res = await GET();
    expect(res.status).toBe(503);
    const body = await res.json();
    expect(body.status).toBe("unavailable");
    expect(body.machines).toBeUndefined();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("returns unavailable when upstream cannot be reached", async () => {
    process.env.TAO_WEBHOOK_SECRET = SECRET;
    fetchMock.mockRejectedValue(new Error("connect"));
    const { GET } = await import("../app/api/mesh-fleet/route");
    const res = await GET();
    expect(res.status).toBe(503);
    expect((await res.json()).status).toBe("unavailable");
  });

  it("projects three machines and never echoes the secret", async () => {
    process.env.TAO_WEBHOOK_SECRET = SECRET;
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify(UPSTREAM), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const { GET } = await import("../app/api/mesh-fleet/route");
    const res = await GET();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.status).toBe("ok");
    expect(body.machines).toHaveLength(3);
    expect(body.machines[0].revision).toBe("mesh-runner@a1b2");
    expect(body.machines[0].currentClaim).toBe("UNI-2649");
    expect(body.checkedAt).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    expect(JSON.stringify(body)).not.toContain(SECRET);
    expect(fetchMock.mock.calls[0][0]).toBe("http://pi-ceo.test/api/mesh/fleet");
    const headers = fetchMock.mock.calls[0][1]?.headers as Record<string, string>;
    expect(headers["X-Pi-CEO-Secret"]).toBe(SECRET);
  });

  it("503s when the machines source failed even if the list is empty", async () => {
    process.env.TAO_WEBHOOK_SECRET = SECRET;
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          machines: [],
          claims: [],
          errors: [{ source: "machines", reason: "not-json" }],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    const { GET } = await import("../app/api/mesh-fleet/route");
    const res = await GET();
    expect(res.status).toBe(503);
    expect((await res.json()).status).toBe("unavailable");
  });
});

describe("proxy gates /api/mesh-fleet", () => {
  it("401s an anonymous GET so the secret-bearing aggregate is not public", async () => {
    const { NextRequest } = await import("next/server");
    const { proxy } = await import("../proxy");
    const res = await proxy(new NextRequest(new URL("https://pi.invalid/api/mesh-fleet")));
    expect(res.status).toBe(401);
  });
});
