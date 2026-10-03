import { mkdirSync, writeFileSync } from "node:fs";
import { expect, test, type Browser, type Page } from "@playwright/test";

// RA-7898 A6 — every existing page renders the same before (main) and after
// (this branch). Two servers, same frozen clock, same routed responses, same
// viewport; screenshots compared byte for byte. Run with:
//   BOARDS_BEFORE_URL=http://127.0.0.1:3011 BOARDS_AFTER_URL=http://127.0.0.1:3010 \
//   BOARDS_A6_DIR=<dir> npx playwright test e2e/boards-unchanged.spec.ts
const BEFORE = process.env.BOARDS_BEFORE_URL;
const AFTER = process.env.BOARDS_AFTER_URL;
const OUT = process.env.BOARDS_A6_DIR ?? "test-results/a6";
const FROZEN = new Date("2026-10-03T00:00:00Z");

export const A6_PAGES = [
  "/control",
  ...["goal", "swarm", "model", "health", "roles", "build", "runs", "curator", "margot", "pipeline", "terminal"].map((s) => `/control/${s}`),
  "/loop", "/overview",
  "/command-centre", "/command-centre/hermes", "/command-centre/knowledge", "/command-centre/providers",
  "/command-centre/wall", "/command-centre/wiki-graph", "/command-centre/youtube-intent",
];

const iso = (agoS = 0) => new Date(FROZEN.getTime() - agoS * 1000).toISOString();
const FEEDS: Record<string, unknown> = {
  "/api/mesh-fleet": { status: "ok", checkedAt: iso(), machines: [{ host: "Phill_Desktop", revision: "e3dff5e", lastHeartbeat: iso(8), currentClaim: "RA-7898", stale: false }] },
  "/api/mesh-fleet/wall": { generated_at: iso(1), banner: { red: 0, grey: 7 }, fleet: { status: "ok", reason: "", others: [], machines: [] },
    stations: ["Capture", "Shape", "Contract", "Build", "Prove", "Ship", "Learn"].map((name) => ({ id: name.toLowerCase(), name, chip: "GREY", reason: "NO LIVE SOURCE YET" })) },
  "/api/model-fabric": { enabled: true, healthy: true, totals: { calls: 10, failures: 1 }, lanes: { review: { model: "m3", banned: false } } },
  "/api/swarm-status": { state: "SHADOW", autonomous_prs_today: 1, autonomous_prs_limit: 3, green_merges: 4, green_merges_target: 20, last_pr_ts: null, last_pr_url: null },
  "/api/kill-switch": { swarm_enabled_env: true, kill_switch_active: false, escalation_lock_active: false, panic_count_last_hour: 0, approver_allowlist: ["a", "b"], approver_totp_configured: ["a"] },
  "/api/curator-proposals": { total: 0, returned: 0, by_status: {}, proposals: [] },
  "/api/pi-ceo/health": { status: "ok", uptime_s: 3600, swarm_enabled: true, swarm_shadow: true },
  "/api/pi-ceo/api/sessions": [{ id: "s1", repo: "CleanExpo/RA", status: "running", started: FROZEN.getTime() / 1000 - 600 }],
  "/api/pi-ceo/api/projects/health": [{ project_id: "RA", repo: "CleanExpo/RA", overall_health: 86, scores: { security: 86 }, findings_count: {}, deployments: {} }],
  "/api/pi-ceo/api/mission-control/live": { ts: iso(), active_sessions: [], recent_completions: [], throughput: { hourly: [1, 2, 3] } },
  "/api/pi-ceo/api/pipelines": [],
  "/api/pi-ceo/api/idea-pipeline": { snapshot: { intake: "", north_star: "", awaiting: 0, packet: null, verdicts: [], go_required: true, executed: false } },
};

async function capture(browser: Browser, base: string, path: string, file: string): Promise<{ png: Buffer; nav: string }> {
  const context = await browser.newContext({ baseURL: base, viewport: { width: 1280, height: 900 } });
  const page: Page = await context.newPage();
  await page.clock.setFixedTime(FROZEN);
  await page.request.post("/api/auth/login", { data: { password: process.env.DASHBOARD_PASSWORD ?? "dev" } });
  await page.route((url) => url.pathname.startsWith("/api/") && !url.pathname.startsWith("/api/auth/"), (route) => {
    const p = new URL(route.request().url()).pathname;
    const body = FEEDS[p];
    return body === undefined
      ? route.fulfill({ status: 503, contentType: "application/json", body: '{"error":"routed test: not provided"}' })
      : route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.goto(path, { waitUntil: "networkidle" });
  await page.waitForTimeout(2_500);
  // The one declared difference on /control/<section> pages is the new "Boards" subnav link
  // (spec D8). Mask the subnav in the picture; compare its links as text instead.
  const nav = await page.locator('nav[aria-label="Control sections"]').allInnerTexts().then((t) => t.join("|")).catch(() => "");
  const png = await page.screenshot({ path: file, animations: "disabled", caret: "hide",
    mask: [page.locator('nav[aria-label="Control sections"]')] });
  await context.close();
  return { png, nav };
}

test.describe("A6: existing pages unchanged", () => {
  test.skip(!BEFORE || !AFTER, "set BOARDS_BEFORE_URL and BOARDS_AFTER_URL");
  test.setTimeout(120_000);
  for (const path of A6_PAGES) {
    test(path, async ({ browser }) => {
      mkdirSync(OUT, { recursive: true });
      const slug = path.replace(/\//g, "_") || "_root";
      const before = await capture(browser, BEFORE!, path, `${OUT}/${slug}.before.png`);
      const after = await capture(browser, AFTER!, path, `${OUT}/${slug}.after.png`);
      const same = before.png.equals(after.png);
      writeFileSync(`${OUT}/${slug}.result.json`, JSON.stringify({ path, identical_pixels: same, nav_before: before.nav, nav_after: after.nav }, null, 2));
      expect(after.nav.replace(/\n?BOARDS$/i, ""), "only the Boards link is added to the subnav").toBe(before.nav);
      expect(same, `${path}: screenshots differ`).toBe(true);
    });
  }
});
