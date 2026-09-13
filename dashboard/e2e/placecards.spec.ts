import { expect, test, type BrowserContext, type Page } from "@playwright/test";

const HOST = "127.0.0.1";
const PORT = Number(process.env.PLACECARDS_PORT ?? 3010);
const ORIGIN = `http://${HOST}:${PORT}`;
const PATH = "/placecards-prototype.html";

function offOrigin(urls: string[], pageUrl: string): string[] {
  const pageHost = new URL(pageUrl).host;
  return urls.filter((url) => {
    try {
      return new URL(url).host !== pageHost;
    } catch {
      return !url.startsWith(pageUrl);
    }
  });
}

test.describe.serial("Placecards spec v1", () => {
  let context: BrowserContext;
  let page: Page;
  const requestsSeen: string[] = [];

  test.beforeAll(async ({ browser }) => {
    context = await browser.newContext({
      baseURL: ORIGIN,
      viewport: { width: 1280, height: 900 },
    });
    page = await context.newPage();
    page.on("request", (request) => {
      requestsSeen.push(request.url());
    });
    const password = process.env.DASHBOARD_PASSWORD ?? "dev";
    const login = await page.request.post("/api/auth/login", {
      data: { password },
    });
    expect(login.ok(), `login failed: ${login.status()} ${await login.text()}`).toBeTruthy();
  });

  test.afterAll(async () => {
    await context.close();
  });

  test("S0 board renders, card opens, spark gate already satisfied", async () => {
    await page.goto(PATH);
    await page.getByTestId("card-tile-c1").click();
    await expect(page.getByTestId("chip-stage")).toHaveText("Stage: spark");
    await expect(page.getByTestId("advance-btn")).toBeEnabled();
    await page.getByTestId("advance-btn").click();
    await expect(page.getByTestId("chip-stage")).toHaveText("Stage: grill");
    await expect(page.getByTestId("move-log").locator("li")).toHaveCount(1);
  });

  test("S1 a gate blocks an early advance", async () => {
    await page.getByTestId("ans-customer").fill(
      "Restoration techs on site; the business owner pays.",
    );
    await page.getByTestId("ans-metric").fill(
      "80% of jobs have photos attached within 1 hour of arrival.",
    );
    const btn = page.getByTestId("advance-btn");
    await expect(btn).toBeDisabled();
    await expect(btn).toContainText("(1 item left)");
    await expect(page.getByTestId("chip-stage")).toHaveText("Stage: grill");
    await expect(page.getByTestId("move-log").locator("li")).toHaveCount(1);
  });

  test("S2 the gate passes and the move is logged exactly once", async () => {
    await page.getByTestId("ans-problem").fill(
      "Photos live on techs' phones and never reach the job file.",
    );
    const btn = page.getByTestId("advance-btn");
    await expect(btn).toBeEnabled();
    await btn.click();
    await expect(page.getByTestId("chip-stage")).toHaveText("Stage: shape");
    await expect(page.getByTestId("move-log").locator("li")).toHaveCount(2);
    await expect(
      page.getByTestId("move-log").locator("li", { hasText: "grill → shape" }),
    ).toHaveCount(1);
  });

  test("S3 a sketch round-trips as human evidence", async () => {
    await page.getByTestId("tab-sketch").click();
    await page.getByTestId("sketch-save").click();
    await expect(page.getByTestId("sketch-status")).toHaveText("Scene saved to the card.");
    await page.getByTestId("tab-evidence").click();
    const row = page.getByTestId("evidence-list").locator("li", { hasText: "excalidraw_scene" });
    await expect(row).toHaveCount(1);
    await expect(row.locator(".tag")).toHaveText("human");
    await page.getByTestId("tab-sketch").click();
    await expect(page.getByTestId("sketch-status")).toHaveText("Scene saved to the card.");
  });

  test("S4 shape and spec gates enforce their checklists", async () => {
    await expect(page.getByTestId("advance-btn")).toBeDisabled();
    await page.getByTestId("appetite-select").selectOption("big_batch");
    await page.getByTestId("fence-input").fill("No auto-tagging or AI classification in v1.");
    await page.getByTestId("fence-add").click();
    await expect(page.getByTestId("advance-btn")).toBeEnabled();
    await page.getByTestId("advance-btn").click();
    await expect(page.getByTestId("chip-stage")).toHaveText("Stage: spec");
    await page.getByTestId("tab-recipe").click();
    await page.getByTestId("schema-text").fill("job_photos(id, job_id, url, taken_at, uploaded_by)");
    await page.getByTestId("schema-add").click();
    for (const gherkin of [
      "Given a tech on site When they upload a photo Then it attaches to the job record",
      "Given no signal When a photo is taken Then it queues and syncs later",
      "Given a duplicate upload When it is detected Then only one copy is kept",
    ]) {
      await page.getByTestId("gherkin-text").fill(gherkin);
      await page.getByTestId("gherkin-add").click();
    }
    await expect(page.getByTestId("gherkin-count")).toContainText("3");
    await expect(page.getByTestId("advance-btn")).toBeEnabled();
    await page.getByTestId("advance-btn").click();
    await expect(page.getByTestId("chip-stage")).toHaveText("Stage: bet");
  });

  test("S5 a decision is recorded, not executed", async () => {
    await page.getByTestId("tab-decision").click();
    await page.getByTestId("decision-go").check();
    await page.getByTestId("decision-reason").fill("Clear pain, small bet, tests already written.");
    await page.getByTestId("decision-record").click();
    await expect(page.getByTestId("chip-stage")).toHaveText("Stage: graduated");
    await expect(page.getByTestId("decision-summary")).toContainText("go");
    await expect(
      page.getByTestId("move-log").locator("li", { hasText: "bet → graduated" }),
    ).toHaveCount(1);
    const external = offOrigin(requestsSeen, page.url());
    expect(external, `external calls fired: ${external.join(", ")}`).toEqual([]);
  });
});
