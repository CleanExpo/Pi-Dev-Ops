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
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, it, expect } from "vitest";
import { allowed } from "@/lib/pi-ceo-proxy-allowlist";
import { PROXY_ANALYZE_MS, PROXY_DEFAULT_MS, proxyAbortPayload, proxyTimeoutMs } from "@/lib/pi-ceo-proxy-timeout";

/**
 * Every proxied surface the smoke suite declares, read from smoke-surfaces.json
 * rather than copied into this file.
 *
 * The hand-copied list below caught the 2026 regression it was written for, then
 * missed the next one for the same reason it existed: PR #650 declared four
 * `/api/nexus/youtube-intent/*` probes expecting 200/422, nobody added them to
 * ALLOWED_UPSTREAM or to this file's array, and the e2e suite went red on main on
 * those four for days. A list maintained by hand drifts from the thing it claims
 * to pin. Deriving it means a surface can never again be declared and silently
 * refused — adding the probe is what makes this test demand the allowlist entry.
 */
function declaredProxySurfaces(): string[] {
  const raw = readFileSync(
    join(process.cwd(), "..", ".github", "smoke-surfaces.json"), "utf-8");
  const surfaces = JSON.parse(raw).horizontal as Array<{
    path: string; auth?: boolean; expected_status?: number;
  }>;
  return surfaces
    // auth:false probes are refused earlier by proxy.ts's session check and never
    // reach this gate; a probe that EXPECTS 403 is asserting the refusal itself.
    .filter((s) => s.auth === true && s.expected_status !== 403)
    .filter((s) => s.path.startsWith("/api/pi-ceo/"))
    .map((s) => s.path.replace(/^\/api\/pi-ceo/, "").split("?")[0]);
}

describe("pi-ceo proxy ALLOWED_UPSTREAM", () => {
  it("admits every proxied surface declared in smoke-surfaces.json", () => {
    const declared = declaredProxySurfaces();
    // Guard against a silently-empty derivation: a parse or path change that
    // returned [] would make this test vacuously pass and prove nothing.
    expect(declared.length).toBeGreaterThan(5);
    const refused = declared.filter((p) => !allowed(p));
    expect(refused, `declared in smoke-surfaces.json but refused by the proxy: ${refused.join(", ")}`)
      .toEqual([]);
  });

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
      "/api/goal-projects",
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

  it("gives goal analyze a long enough window that a 25s LLM call is not a 502", () => {
    expect(proxyTimeoutMs("/api/goal-ticket/analyze")).toBe(PROXY_ANALYZE_MS);
    expect(proxyTimeoutMs("/api/goal-ticket/analyze?x=1")).toBe(PROXY_ANALYZE_MS);
    expect(proxyTimeoutMs("/api/goal-ticket")).toBe(PROXY_DEFAULT_MS);
    expect(proxyTimeoutMs("/api/health")).toBe(PROXY_DEFAULT_MS);
    expect(PROXY_ANALYZE_MS).toBeGreaterThan(25_000);
  });

  it("names a timeout distinctly from unreachable so analyze is not a fake 502", () => {
    const timed = proxyAbortPayload({ name: "TimeoutError" });
    expect(timed.status).toBe(504);
    expect(timed.error).toMatch(/timed out/i);
    const down = proxyAbortPayload(new Error("connect"));
    expect(down.status).toBe(502);
  });
});
