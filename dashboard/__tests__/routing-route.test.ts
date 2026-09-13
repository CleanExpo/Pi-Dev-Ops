/**
 * GET /api/routing is the dashboard half of RA-7434. Production smoke 404'd
 * because FastAPI registered the route and Vercel did not.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

const piCeoFetch = vi.fn();

vi.mock("@/lib/pi-ceo-session", () => ({
  piCeoFetch: (...args: unknown[]) => piCeoFetch(...args),
}));

beforeEach(() => {
  piCeoFetch.mockReset();
});

afterEach(() => {
  vi.resetModules();
});

describe("GET /api/routing", () => {
  it("proxies a Railway 200 payload unchanged", async () => {
    const payload = {
      day_iso: "2026-09-13",
      tenant_id: "pi-ceo",
      cost_source: null,
      cost_reason: "supabase not configured",
      roles: { planner: { provider: "anthropic", model: "claude-sonnet-5" } },
      margot_casual: { ladder: [], ollama_configured: false },
    };
    piCeoFetch.mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const { GET } = await import("../app/api/routing/route");
    const res = await GET();
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual(payload);
    expect(piCeoFetch).toHaveBeenCalledWith("/api/routing", {}, 8_000);
  });

  it("503s when Railway cannot be reached, rather than inventing roles", async () => {
    piCeoFetch.mockResolvedValue(null);
    const { GET } = await import("../app/api/routing/route");
    const res = await GET();
    expect(res.status).toBe(503);
    const body = await res.json();
    expect(body.roles).toBeUndefined();
    expect(body.error).toMatch(/unavailable/i);
  });
});
