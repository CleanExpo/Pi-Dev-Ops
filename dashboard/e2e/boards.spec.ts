import { expect, test, type Page } from "@playwright/test";

import { routeFeeds } from "./boards-fixtures";

// RA-7898 acceptance on /control/boards (docs/specs/modular-boards.md §9).
// Every feed is routed to synthetic test responses (boards-fixtures.ts).
const STORAGE_KEY = "pi-boards-v1";
const SHOTS = process.env.BOARDS_SHOT_DIR;

async function login(page: Page): Promise<void> {
  const res = await page.request.post("/api/auth/login", { data: { password: process.env.DASHBOARD_PASSWORD ?? "dev" } });
  expect(res.ok()).toBeTruthy();
}

async function seed(page: Page, board: unknown): Promise<void> {
  await page.addInitScript(([key, value]) => {
    if (!sessionStorage.getItem("seeded")) { localStorage.setItem(key, value); sessionStorage.setItem("seeded", "1"); }
  }, [STORAGE_KEY, JSON.stringify({ order: ["t"], active: "t", boards: { t: board } })] as const);
}

const card = (page: Page, id: string) => page.locator(`[data-item="${id}"]`);
const stored = (page: Page) => page.evaluate((k) => JSON.parse(localStorage.getItem(k) ?? "null"), STORAGE_KEY);

async function shot(page: Page, name: string): Promise<void> {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: false });
}

test.beforeEach(async ({ page }) => { await login(page); });

test("A1: drag, resize, add, remove and switch a view; all five survive a reload", async ({ page }) => {
  await routeFeeds(page, "healthy");
  await page.goto("/control/boards");
  await expect(page.getByTestId("boards-page")).toBeVisible();
  await expect(card(page, "clock-1").locator("article")).toHaveAttribute("data-state", "live");
  await shot(page, "desk-paper");
  await page.getByRole("button", { name: "Customize" }).click();
  await shot(page, "desk-customize");
  // The library drawer opens with Customize and sits over the right edge; close it to reach that column.
  await page.getByRole("complementary", { name: "Module library" }).getByRole("button", { name: "Close" }).click();

  // Resize the Builds number taller by its corner (left column: the app shell's Margot bubble covers the bottom-right corner of the viewport).
  const corner = await card(page, "builds-n").locator(".react-resizable-handle").boundingBox();
  await page.mouse.move(corner!.x + corner!.width / 2, corner!.y + corner!.height / 2);
  await page.mouse.down();
  await page.mouse.move(corner!.x + 10, corner!.y + 80, { steps: 10 });
  await page.mouse.up();
  await page.waitForTimeout(500);
  const resized = (await stored(page))?.boards.desk.layouts.lg.find((c: { i: string }) => c.i === "builds-n");
  expect(resized?.h, "resize saved").toBeGreaterThan(4);
  // Drag the clock left by its title (scrolled into view: the resize can scroll the board).
  await card(page, "clock-1").scrollIntoViewIfNeeded();
  await page.locator("[data-testid=boards-page]").evaluate((el) => { el.scrollTop = 0; });
  await page.waitForTimeout(300);
  const handle = await card(page, "clock-1").locator(".mc-drag").boundingBox();
  await page.mouse.move(handle!.x + 20, handle!.y + 8);
  await page.mouse.down();
  await page.mouse.move(handle!.x - 250, handle!.y + 8, { steps: 12 });
  await page.mouse.move(handle!.x - 480, handle!.y + 10, { steps: 12 });
  await page.mouse.up();
  await page.waitForTimeout(500); // cards animate into place for 200 ms
  // Add a Wiki graph tile from the library; remove the Ideas funnel; switch Models to Table.
  await page.getByRole("button", { name: "+ Add module" }).click();
  await page.getByRole("button", { name: "Add Wiki graph as Summary tile" }).click();
  await page.getByRole("complementary", { name: "Module library" }).getByRole("button", { name: "Close" }).click();
  await card(page, "ideas-1").getByRole("button", { name: "Options for Ideas" }).click();
  await page.getByRole("menuitem", { name: "Remove from board" }).click();
  await card(page, "models-1").getByRole("button", { name: "Table" }).click();

  const before = await stored(page);
  const desk = before.boards.desk;
  const lg = (id: string) => desk.layouts.lg.find((c: { i: string }) => c.i === id);
  // The preset puts the clock at x 6, y 0; the drag must have moved it.
  expect([lg("clock-1").x, lg("clock-1").y]).not.toEqual([6, 0]);
  expect(lg("builds-n").h).toBeGreaterThan(4);
  expect(desk.items.some((i: { module: string }) => i.module === "wiki-graph")).toBe(true);
  expect(desk.items.some((i: { id: string }) => i.id === "ideas-1")).toBe(false);
  expect(desk.items.find((i: { id: string }) => i.id === "models-1").view).toBe("table");

  await page.reload();
  await expect(page.getByTestId("boards-page")).toBeVisible();
  expect((await stored(page)).boards.desk).toEqual(desk);
  await expect(card(page, "ideas-1")).toHaveCount(0);
  await expect(page.locator('[data-module="wiki-graph"]')).toHaveCount(1);
  await expect(card(page, "models-1").locator("article")).toHaveAttribute("data-view", "table");
});

const twoFleets = { name: "Two fleets", skin: "paper", items: [
  { id: "f1", module: "fleet", view: "tile" }, { id: "f2", module: "fleet", view: "list" },
], layouts: { lg: [{ i: "f1", x: 0, y: 0, w: 6, h: 5 }, { i: "f2", x: 6, y: 0, w: 6, h: 5 }] } };

test("A2: two Fleet modules make one /api/mesh-fleet request per 20 s", async ({ page }) => {
  test.setTimeout(90_000);
  await routeFeeds(page, "healthy");
  await seed(page, twoFleets);
  const hits: number[] = [];
  page.on("request", (r) => { if (new URL(r.url()).pathname === "/api/mesh-fleet") hits.push(Date.now()); });
  await page.goto("/control/boards");
  await expect(card(page, "f2").locator("article")).toHaveAttribute("data-state", "live");
  await page.waitForTimeout(21_000);
  // Two modules, one poller: exactly the first read and one more ~20 s later.
  expect(hits.length).toBe(2);
  expect(hits[1] - hits[0]).toBeGreaterThan(15_000);
});

test("A3: Pi-CEO backend down — no module shows a number; provider-usage and wiki-graph stay live", async ({ page }) => {
  await routeFeeds(page, "down");
  await page.goto("/control/boards");
  const frames = page.locator("article[data-module]");
  await expect(frames.first()).toBeVisible();
  await expect(card(page, "fleet-1").locator("article")).toHaveAttribute("data-state", /unreachable|stale/);
  await page.waitForTimeout(1_500);
  await shot(page, "desk-backend-down");
  for (const id of ["builds-n", "ship-chain-1", "models-1", "fleet-1", "activity-1", "builds-1", "portfolio-1", "ideas-1", "kill-switch-1"]) {
    const frame = card(page, id).locator("article");
    await expect(frame, id).toHaveAttribute("data-state", /unreachable|stale/);
    const body = await frame.locator(":scope > div").last().innerText();
    expect(body, `${id} shows a number while its source is down`).not.toMatch(/\d/);
  }
  await expect(card(page, "kill-switch-1").getByRole("button", { name: "Halt swarm" })).toBeEnabled();
  await seed(page, { name: "Local", skin: "paper", items: [
    { id: "pu", module: "provider-usage", view: "cockpit" }, { id: "wg", module: "wiki-graph", view: "tile" }],
  layouts: { lg: [{ i: "pu", x: 0, y: 0, w: 8, h: 10 }, { i: "wg", x: 8, y: 0, w: 4, h: 4 }] } });
  await page.goto("/control/boards");
  await expect(card(page, "pu").locator("article")).toHaveAttribute("data-state", "live");
  await expect(card(page, "wg").locator("article")).toHaveAttribute("data-state", "live");
});

test("A4: an unknown module id renders the grey frame and the page keeps working", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await routeFeeds(page, "healthy");
  await seed(page, { name: "Odd", skin: "graphite", items: [
    { id: "x", module: "launch-missiles", view: "now" }, { id: "c", module: "clock", view: "digital" }],
  layouts: { lg: [{ i: "x", x: 0, y: 0, w: 6, h: 4 }, { i: "c", x: 6, y: 0, w: 3, h: 3 }] } });
  await page.goto("/control/boards");
  await expect(page.getByRole("heading", { name: "Unknown module “launch-missiles”" })).toBeVisible();
  await expect(card(page, "c").locator("article")).toHaveAttribute("data-state", "live");
  expect(errors).toEqual([]);
});

test("A7: at 400 px wide there is no horizontal page scroll and modules stack", async ({ page }) => {
  await page.setViewportSize({ width: 400, height: 900 });
  await routeFeeds(page, "healthy");
  await page.goto("/control/boards");
  await expect(card(page, "clock-1").locator("article")).toBeVisible();
  await shot(page, "desk-phone-400");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  // Cards animate into place; poll until they settle into one column.
  await expect.poll(async () => {
    const xs = await page.locator("[data-item]").evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().left)));
    return new Set(xs).size;
  }).toBe(1);
});

test("A10: the kiosk shows a preset full-screen, locked, with the machine passed through", async ({ page }) => {
  await routeFeeds(page, "healthy");
  await page.goto("/control/boards/kiosk?board=wall-1&machine=Phill_Desktop");
  await expect(page.getByTestId("kiosk")).toBeVisible();
  await expect(page.locator("article[data-module]").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Customize" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Options for/ })).toHaveCount(0);
  await page.waitForTimeout(1_000);
  await shot(page, "kiosk-wall-1");
  await page.goto("/control/boards/kiosk?board=nope");
  await expect(page.getByRole("alert")).toContainText("Valid ids: desk, founder-brief, wall-1");
});

for (const skin of ["graphite", "slate"] as const) {
  test(`look: ${skin}`, async ({ page }) => {
    test.skip(!SHOTS, "screenshots only");
    await routeFeeds(page, "healthy");
    await page.goto("/control/boards");
    await page.getByRole("button", { name: skin[0].toUpperCase() + skin.slice(1) }).click();
    await page.waitForTimeout(800);
    await shot(page, `desk-${skin}`);
  });
}
