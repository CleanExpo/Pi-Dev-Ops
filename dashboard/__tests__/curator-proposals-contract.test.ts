/**
 * The curator-proposals allow-list must accept what upstream actually sends.
 *
 * The route validates the upstream payload against a set of key paths and fails CLOSED —
 * it withholds the body and returns "upstream payload shape changed". The list named
 * `proposals[].id`, `.skill`, `.summary`, `.rationale`; upstream has never sent those. It
 * emits `proposal_id`, `proposed_skill_name`, `cluster_summary`, `ts`, and has since
 * 2026-07-01 (swarm/meta_curator.py, 040f54eb) — a month before the list was written on
 * 2026-08-03 (#609). Every response therefore failed, and the panel has been dark in
 * production since it shipped. Vercel runtime errors, 2026-08-18T13:04–13:06, 5 occurrences.
 *
 * The fixture below is the REAL payload, assembled from the record at
 * swarm/meta_curator.py:518-529 and the response at app/server/routes/swarm.py:251-258.
 * Using the shape production actually rejected is the point: a fixture invented to match the
 * new list would pass no matter what the list said.
 */
import { describe, it, expect } from "vitest";

/** Mirrors `keyPaths` in app/api/curator-proposals/route.ts. */
function keyPaths(value: unknown, prefix = ""): string[] {
  if (Array.isArray(value)) return value.flatMap((item) => keyPaths(item, `${prefix}[]`));
  if (!value || typeof value !== "object") return [];
  return Object.entries(value as Record<string, unknown>).flatMap(([key, item]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return [path, ...keyPaths(item, path)];
  });
}

const ALLOWED_PATHS = new Set([
  "total", "returned", "by_status", "proposals", "error", "detail",
  "count", "status", "limit",
  "proposals[].ts", "proposals[].proposal_id", "proposals[].cluster_id",
  "proposals[].trigger_source", "proposals[].cluster_summary",
  "proposals[].evidence_count", "proposals[].proposed_skill_name",
  "proposals[].proposed_skill_path", "proposals[].status",
  "proposals[].created_at", "proposals[].draft_id", "proposals[].reason",
]);

function isAllowedPath(path: string): boolean {
  if (ALLOWED_PATHS.has(path)) return true;
  return /^by_status\.[^.]+$/.test(path);
}

/** The exact shape app/server/routes/swarm.py:251-258 returns. */
const UPSTREAM_PAYLOAD = {
  total: 2,
  returned: 2,
  by_status: { pending: 1, queued_dry_run: 1 },
  proposals: [
    {
      ts: "2026-08-18T13:04:17+00:00",
      proposal_id: "a1b2c3d4e5f6",
      cluster_id: "cluster-7",
      trigger_source: "scanner",
      cluster_summary: "repeated null-check omissions in route handlers",
      evidence_count: 4,
      proposed_skill_name: "null-check-discipline",
      proposed_skill_path: "skills/null-check-discipline/SKILL.md",
      status: "pending",
      created_at: "2026-08-18T13:04:17+00:00",
    },
  ],
};

describe("curator-proposals upstream contract", () => {
  it("accepts the payload production actually sends", () => {
    const unexpected = [...new Set(keyPaths(UPSTREAM_PAYLOAD))].filter((k) => !isAllowedPath(k));

    expect(unexpected).toEqual([]);
  });

  it("accepts any status key under by_status, not just the ones seen so far", () => {
    // by_status is Record<string, number>. Allow-listing bare `by_status` was the bug:
    // `by_status.pending` tripped the guard, and so would every other status.
    const payload = {
      by_status: {
        pending: 1, accepted: 2, rejected_dedup: 1, rejected_cooloff: 1,
        rejected_rate: 1, expired: 3, queued_dry_run: 1, unknown: 1,
      },
    };

    const unexpected = [...new Set(keyPaths(payload))].filter((k) => !isAllowedPath(k));

    expect(unexpected).toEqual([]);
  });

  it("still rejects a genuinely unknown key, so the guard has not been widened away", () => {
    // Negative control. Without this, an allow-list that permitted everything would pass
    // both tests above — which is the failure mode this guard exists to catch.
    const payload = { ...UPSTREAM_PAYLOAD, surprise_field: "unexpected" };

    const unexpected = [...new Set(keyPaths(payload))].filter((k) => !isAllowedPath(k));

    expect(unexpected).toContain("surprise_field");
  });

  it("does not allow arbitrary depth under by_status", () => {
    // The wildcard is one level only; a nested object there would still be a shape change.
    const payload = { by_status: { pending: { nested: 1 } } };

    const unexpected = [...new Set(keyPaths(payload))].filter((k) => !isAllowedPath(k));

    expect(unexpected).toContain("by_status.pending.nested");
  });
});
