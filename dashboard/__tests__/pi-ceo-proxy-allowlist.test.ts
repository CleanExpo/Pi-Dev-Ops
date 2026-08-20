/**
 * ALLOWED_UPSTREAM (app/api/pi-ceo/[...path]/route.ts) is a deliberate security allowlist —
 * unlisted paths are refused rather than forwarded to the Pi CEO backend. Its own commit
 * message claimed "16/16 legitimate paths admitted" but that verification was never captured
 * as a test, so the enumeration silently regressed: 8 pre-existing, still-smoke-tested routes
 * (some pre-dating the allowlist itself) fell out and started 403ing in production for over a
 * week before anyone noticed. This test pins the routes the E2E smoke suite's `auth: true`
 * probes require (.github/smoke-surfaces.json — those are the only probes that ever reach this
 * gate; `auth: false` probes are blocked earlier by proxy.ts's session check and never
 * exercise this allowlist at all), and keeps a hostile-path check alongside so a fix here can't
 * silently widen the gate into a catch-all again.
 */
import { describe, it, expect } from "vitest";
import { allowed } from "@/app/api/pi-ceo/[...path]/route";

describe("pi-ceo proxy ALLOWED_UPSTREAM", () => {
  it("admits every auth:true route the smoke suite depends on", () => {
    const legitimate = [
      "/api/autonomy/status",
      "/api/integrations/health",
      "/api/telegram/intake/status",
      "/api/health/full",
      "/api/nexus/health",
      "/api/nexus/ingest/health",
      "/webhook/telegram",
      "/api/sessions/abc123/logs/stream",
      "/api/spec-pipeline/run",
      "/api/sessions/abc123/kill",
      // Pre-existing routes — must not regress.
      "/health",
      "/api/health",
      "/api/health/obsidian",
      "/api/sessions",
      "/api/sessions/abc123/logs",
      "/api/sessions/abc123/stream",
      "/api/sessions/abc123/resume",
      "/api/spec-pipeline",
      "/api/mission-control/live",
      "/api/goal-ticket",
      "/api/goal-ticket/analyze",
    ];
    for (const path of legitimate) {
      expect(allowed(path), `expected ${path} to be allowed`).toBe(true);
    }
  });

  it("still refuses paths outside the allowlist", () => {
    const hostile = [
      "/api/login",
      "/api/anything/random",
      "/api/sessions/abc/kill/extra",
      "/api/autonomy/status/../../login",
      "/webhook/telegram/extra",
    ];
    for (const path of hostile) {
      expect(allowed(path), `expected ${path} to be refused`).toBe(false);
    }
  });

  it("compares the path only — a query string cannot widen what is reachable", () => {
    expect(allowed("/api/autonomy/status?x=1")).toBe(true);
    expect(allowed("/api/login?path=/api/autonomy/status")).toBe(false);
  });
});
