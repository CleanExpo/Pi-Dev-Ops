import { defineConfig, devices } from "@playwright/test";

// WP-02 (docs/plans/mission-control/work-packages.md): the Mission Control
// suite that runs against a DEPLOYED dashboard, never a local stub server.
// Target comes from MC_LIVE_URL; sign-in uses DASHBOARD_PASSWORD. Both are
// supplied by .github/workflows/mission-control-live.yml.
const baseURL = process.env.MC_LIVE_URL ?? "https://pi-dev-ops.vercel.app";
const isCI = Boolean(process.env.CI);

export default defineConfig({
  testDir: "./e2e-live",
  testMatch: "**/*.spec.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 20_000 },
  retries: 0,
  reporter: isCI ? [["github"], ["list"]] : "list",
  use: {
    ...devices["Desktop Chrome"],
    baseURL,
    viewport: { width: 1440, height: 900 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    // Local containers may ship a different Chromium build than this
    // Playwright version expects; CI installs the matching one.
    launchOptions: process.env.PW_CHROMIUM_PATH
      ? { executablePath: process.env.PW_CHROMIUM_PATH }
      : {},
  },
});
