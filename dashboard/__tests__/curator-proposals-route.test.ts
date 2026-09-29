/**
 * RA-7848: /api/curator-proposals withheld every real proposal. Its allowlist
 * named fields the backend never sends (id / skill / summary / rationale) and
 * had no room for by_status counts, so any non-empty response became
 * "upstream payload shape changed". The payload below has the shape
 * app/server/routes/swarm.py::curator_proposals returns for records written
 * by swarm/meta_curator.py.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const piCeoFetch = vi.fn();

vi.mock("@/lib/pi-ceo-session", () => ({
  piCeoFetch: (...args: unknown[]) => piCeoFetch(...args),
  isLockedOut: () => false,
}));

const BACKEND_PAYLOAD = {
  total: 3,
  returned: 2,
  by_status: { pending: 1, rejected_dedup: 1, accepted: 1 },
  proposals: [
    {
      ts: "2026-09-29T09:00:00+00:00",
      proposal_id: "a1b2c3d4e5f6",
      cluster_id: "lessons:flaky-ci",
      trigger_source: "lessons",
      cluster_summary: "Flaky CI retried by hand",
      evidence_count: 5,
      proposed_skill_name: "retry-flaky-ci",
      proposed_skill_path: "skills/retry-flaky-ci/SKILL.md",
      status: "pending",
      created_at: "2026-09-29T09:00:00+00:00",
      draft_id: "d-1",
    },
    {
      ts: "2026-09-28T09:00:00+00:00",
      cluster_id: "pr:dup",
      status: "rejected_dedup",
      proposed_skill_name: "existing-skill",
      reason: "skill name already exists",
    },
  ],
};

function upstream(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
}

beforeEach(() => {
  piCeoFetch.mockReset();
  vi.stubEnv("PI_CEO_URL", "https://backend.test");
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("GET /api/curator-proposals", () => {
  it("passes a real backend payload through unchanged", async () => {
    piCeoFetch.mockResolvedValue(upstream(BACKEND_PAYLOAD));
    const { GET } = await import("../app/api/curator-proposals/route");
    const res = await GET(new Request("http://dash.test/api/curator-proposals?status=pending&limit=10"));
    expect(await res.json()).toEqual(BACKEND_PAYLOAD);
    expect(piCeoFetch.mock.calls[0][0]).toBe("/api/swarm/curator/proposals?status=pending&limit=10");
  });

  it("still withholds a field it does not know (the full skill body)", async () => {
    const leaky = { ...BACKEND_PAYLOAD, proposals: [{ ...BACKEND_PAYLOAD.proposals[0], proposed_skill_content: "# SKILL" }] };
    piCeoFetch.mockResolvedValue(upstream(leaky));
    const { GET } = await import("../app/api/curator-proposals/route");
    const body = await (await GET(new Request("http://dash.test/api/curator-proposals"))).json();
    expect(body.error).toBe("upstream payload shape changed");
    expect(body.proposals).toEqual([]);
  });

  it("withholds anything nested under a status count", async () => {
    piCeoFetch.mockResolvedValue(upstream({ ...BACKEND_PAYLOAD, by_status: { pending: { note: "internal" } } }));
    const { GET } = await import("../app/api/curator-proposals/route");
    const body = await (await GET(new Request("http://dash.test/api/curator-proposals"))).json();
    expect(body.error).toBe("upstream payload shape changed");
    expect(JSON.stringify(body)).not.toContain("internal");
  });
});
