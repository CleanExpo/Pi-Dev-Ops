import { expect, test, type Page } from "@playwright/test";

// /control command wall smoke. Every upstream source is synthetic and routed;
// screenshots land in test-results/command-wall/ for the PR body.
const NOW = new Date().toISOString();
const WALL = {
  generated_at: NOW,
  banner: { red: 0, grey: 1 },
  fleet: {
    status: "ok", reason: "", others: [],
    machines: [
      { host: "Phills-MacBook-Pro", chip: "GREEN", reason: "reporting", ageSeconds: 8, load1: 2.1, selfReported: true,
        agents: [{ runtime: "claude", state: "busy", chip: "GREEN", ageSeconds: 3 }] },
      { host: "Phills-Mac-mini", chip: "GREEN", reason: "reporting", ageSeconds: 14, load1: 0.7, selfReported: true,
        agents: [{ runtime: "codex", state: "idle", chip: "GREEN", ageSeconds: 9 }] },
      { host: "Phill_Desktop", chip: "GREY", reason: "no signal", ageSeconds: 1800, load1: null, selfReported: true, agents: [] },
    ],
  },
  stations: [],
};

function flowBoard(repo: string) {
  if (repo === "CleanExpo/CCW-CRM") {
    return { ok: false, checked_at: NOW, error: "GitHub unavailable: GitHub pulls HTTP 404", repo,
      columns: { shipped: [], audit: [], phill: [], aging: [] },
      pull_requests: { status: "unavailable", reason: "GitHub pulls HTTP 404" }, ci: { status: "unavailable", reason: "GitHub CI HTTP 404" } };
  }
  const pr = (n: number, column: string) => ({ id: `PR-${n}`, title: `PR ${n}`, url: `https://github.com/${repo}/pull/${n}`,
    lane: "engineer", column, ageDays: column === "aging" ? 6 : 1, tone: "ok", receipts: "" });
  return { ok: true, checked_at: NOW, error: null, repo,
    columns: { shipped: [], audit: [pr(11, "audit"), pr(12, "audit")], phill: [pr(13, "phill")], aging: [pr(9, "aging")] },
    pull_requests: { status: "ok", value: { count: 4, capped: false } },
    ci: { status: "ok", value: { branch: "main", sha: "abc1234", state: repo.endsWith("carsi") ? "failure" : "success" } } };
}

async function stub(page: Page) {
  await page.route((url) => url.pathname.startsWith("/api/") && !url.pathname.startsWith("/api/auth/"), (route) => {
    const url = new URL(route.request().url());
    const body = url.pathname === "/api/mesh-fleet/wall" ? WALL
      : url.pathname === "/api/mesh-fleet" ? { status: "unavailable", checkedAt: NOW, reason: "mesh secret not configured" }
      : url.pathname === "/api/flow-board" ? flowBoard(url.searchParams.get("repo") ?? "")
      : null;
    return body === null
      ? route.fulfill({ status: 503, contentType: "application/json", body: '{"error":"routed test: not provided"}' })
      : route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  const login = await page.request.post("/api/auth/login", { data: { password: process.env.DASHBOARD_PASSWORD ?? "dev" } });
  expect(login.ok()).toBeTruthy();
}

test("the /control wall renders five live screens with honest empty states", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await stub(page);
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto("/control");

  const wall = page.getByTestId("command-wall");
  await expect(wall.getByText("Mac Mini")).toBeVisible();
  await expect(wall.getByText(/claude · busy/)).toBeVisible();
  const prs = page.getByRole("region", { name: "PR pipeline" });
  await expect(prs.getByText("RestoreAssist")).toBeVisible();
  await expect(prs.getByText(/unavailable: GitHub pulls HTTP 404/)).toBeVisible();
  await expect(page.getByRole("region", { name: "Revenue and funnel" }).getByText(/No revenue or funnel source/)).toBeVisible();
  await expect(page.getByRole("region", { name: "CRM to Synthex campaign flow" }).getByText("not connected").first()).toBeVisible();
  await expect(page.getByRole("region", { name: "Alerts and incidents" }).getByText(/carsi main branch CI failing/).first()).toBeVisible();
  await expect(page.getByRole("region", { name: "Portfolio focus" })).toBeAttached();
  await page.waitForTimeout(900);
  await page.screenshot({ path: "test-results/command-wall/desktop-1600.png" });
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.screenshot({ path: "test-results/command-wall/laptop-1280.png", fullPage: false });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "test-results/command-wall/phone-390.png", fullPage: false });
  // On a phone each campaign stage keeps a readable width; the track scrolls instead.
  const nodeWidths = await page.getByRole("list", { name: "CRM to Synthex campaign flow" }).evaluate((ol) =>
    Array.from(ol.querySelectorAll("li > div")).map((el) => el.getBoundingClientRect().width));
  expect(nodeWidths).toHaveLength(7);
  for (const w of nodeWidths) expect(w).toBeGreaterThanOrEqual(132);
  expect(errors).toEqual([]);
});

test("reduced motion: the ticker stops scrolling and drops its loop copy", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await stub(page);
  await page.goto("/control");
  const ticker = page.getByRole("region", { name: "Alerts and incidents" });
  await expect(ticker.getByText(/carsi main branch CI failing/)).toHaveCount(1);
  await expect(ticker.locator("ul")).toHaveAttribute("data-static", "true");
  const animation = await ticker.locator("ul").evaluate((el) => getComputedStyle(el).animationName);
  expect(animation).toBe("none");
  // Static alerts wrap, so the reason at the end of a long alert is never clipped.
  const wrap = await ticker.locator("li").first().evaluate((el) => getComputedStyle(el).whiteSpace);
  expect(wrap).toBe("normal");
});
