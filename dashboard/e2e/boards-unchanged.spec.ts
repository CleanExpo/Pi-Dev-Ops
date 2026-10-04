import { mkdirSync, writeFileSync } from "node:fs";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { A6_FEEDS as FEEDS, FROZEN } from "./a6-feeds";

// RA-7898 A6 — every existing page renders the same before (main) and after
// (this branch). Two servers, same frozen clock, same routed responses, same
// viewport; screenshots compared byte for byte. Run with:
//   BOARDS_BEFORE_URL=http://127.0.0.1:3011 BOARDS_AFTER_URL=http://127.0.0.1:3010 \
//   BOARDS_A6_DIR=<dir> npx playwright test e2e/boards-unchanged.spec.ts
const BEFORE = process.env.BOARDS_BEFORE_URL;
const AFTER = process.env.BOARDS_AFTER_URL;
const OUT = process.env.BOARDS_A6_DIR ?? "test-results/a6";

export const A6_PAGES = [
  "/control",
  ...["goal", "swarm", "model", "health", "roles", "build", "runs", "curator", "margot", "pipeline", "terminal"].map((s) => `/control/${s}`),
  "/loop", "/overview",
  "/command-centre", "/command-centre/hermes", "/command-centre/knowledge", "/command-centre/providers",
  "/command-centre/wall", "/command-centre/wiki-graph", "/command-centre/youtube-intent",
];

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
  // (spec D8). It is appended last, so hiding just that link leaves every other pixel to compare;
  // its presence is asserted as text. Nothing else is masked.
  const navs = page.locator('nav[aria-label="Control sections"]');
  const nav = (await navs.count()) ? (await navs.innerText()) : "";
  await page.addStyleTag({ content: 'nav[aria-label="Control sections"] a[href="/control/boards"] { visibility: hidden !important; }' });
  const png = await page.screenshot({ path: file, animations: "disabled", caret: "hide" });
  await context.close();
  return { png, nav };
}

test.describe("A6: existing pages unchanged", () => {
  // Needs two servers (main and this branch); reported as SKIPPED, never as a pass, when they are not given.
  test.skip(!BEFORE || !AFTER, "A6 needs BOARDS_BEFORE_URL (main) and BOARDS_AFTER_URL (branch) servers");
  test.setTimeout(120_000);
  for (const path of A6_PAGES) {
    test(path, async ({ browser }) => {
      mkdirSync(OUT, { recursive: true });
      const slug = path.replace(/\//g, "_") || "_root";
      const before = await capture(browser, BEFORE!, path, `${OUT}/${slug}.before.png`);
      const after = await capture(browser, AFTER!, path, `${OUT}/${slug}.after.png`);
      const same = before.png.equals(after.png);
      writeFileSync(`${OUT}/${slug}.result.json`, JSON.stringify({ path, identical_pixels: same, nav_before: before.nav, nav_after: after.nav }, null, 2));
      if (path.startsWith("/control/")) {
        expect(before.nav.length, "subnav found on a section page").toBeGreaterThan(0);
        expect(after.nav, "only the Boards link is added to the subnav").toBe(`${before.nav}\nBOARDS`);
      } else {
        expect(after.nav).toBe(before.nav);
      }
      expect(same, `${path}: screenshots differ`).toBe(true);
    });
  }
});
