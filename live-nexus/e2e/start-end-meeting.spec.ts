import { test, expect } from "@playwright/test";

test("landing page renders brand chrome and preflight", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("UNITE GROUP NEXUS")).toBeVisible();
  await expect(page.getByText("Live meeting notes")).toBeVisible();
  // Pre-flight checklist row (exact match — there's also a paragraph below mentioning microphone access)
  await expect(page.getByText("Microphone", { exact: true })).toBeVisible();
});

test("start button redirects to /m/[uuid]", async ({ page, context }) => {
  await context.grantPermissions(["microphone"]);
  // Stub /api/session to return ok so preflight passes
  await page.route("**/api/session", (route) =>
    route.fulfill({
      status: 200,
      body: JSON.stringify({
        token: "x",
        ws_url: "wss://x",
        expires_at: Date.now() + 60000,
      }),
    })
  );
  await page.goto("/");
  // Wait for preflight to settle
  await page.waitForTimeout(800);
  const startButton = page.locator("button:has-text('Start Meeting')");
  await expect(startButton).toBeEnabled({ timeout: 5000 });
  await startButton.click();
  await expect(page).toHaveURL(/\/m\/[\w-]+/);
  await expect(page.getByText("UNITE GROUP NEXUS")).toBeVisible();
});
