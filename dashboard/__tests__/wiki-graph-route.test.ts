/**
 * GET /api/command-centre/wiki-graph must stay a 200 contract for the smoke
 * probe and the Command Centre tile. Missing Vercel credentials used to 503.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

const ENV_KEYS = [
  "SUPABASE_UNITE_GROUP_URL",
  "SUPABASE_UNITE_GROUP_SERVICE_KEY",
  "UGO_SUPABASE_URL",
  "UGO_SUPABASE_SERVICE_KEY",
] as const;

const saved: Record<string, string | undefined> = {};

const piCeoFetch = vi.fn();

vi.mock("@/lib/pi-ceo-session", () => ({
  piCeoFetch: (...args: unknown[]) => piCeoFetch(...args),
}));

beforeEach(() => {
  for (const k of ENV_KEYS) saved[k] = process.env[k];
  for (const k of ENV_KEYS) delete process.env[k];
  piCeoFetch.mockReset();
});

afterEach(() => {
  for (const k of ENV_KEYS) {
    if (saved[k] === undefined) delete process.env[k];
    else process.env[k] = saved[k];
  }
  vi.resetModules();
});

describe("GET /api/command-centre/wiki-graph", () => {
  it("returns a stable empty graph at 200 when no key and Railway is silent", async () => {
    piCeoFetch.mockResolvedValue(null);
    const { GET } = await import("../app/api/command-centre/wiki-graph/route");
    const res = await GET();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.pageCount).toBe(0);
    expect(body.nodes).toEqual([]);
    expect(body.edges).toEqual([]);
    expect(body.source).toBe("unconfigured");
  });

  it("passes through a Railway graph when Vercel has no key", async () => {
    piCeoFetch.mockResolvedValue(
      new Response(
        JSON.stringify({
          nodes: [{ id: "a", title: "A", slug: "a", tags: [], degree: 0 }],
          edges: [],
          pageCount: 1,
          lastSync: null,
          truncated: false,
          edgeCount: 0,
          source: "unite-group",
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    const { GET } = await import("../app/api/command-centre/wiki-graph/route");
    const res = await GET();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.pageCount).toBe(1);
    expect(piCeoFetch).toHaveBeenCalledWith("/api/wiki-graph", {}, 8_000);
  });
});
