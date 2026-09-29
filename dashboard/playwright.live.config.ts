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
    baseURL,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    // Local containers may ship a different Chromium build than this
    // Playwright version expects; CI installs the matching one.
    launchOptions: process.env.PW_CHROMIUM_PATH
      ? { executablePath: process.env.PW_CHROMIUM_PATH }
      : {},
  },
  // MC check 9 (WP-09): checks 1-2 must pass at both sizes, so the read
  // journeys run twice. Level 2 checks and the MC-00 nav check stay desktop
  // only: a phone layout may fold the nav into a menu by design.
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    {
      name: "phone",
      testMatch: "**/read-journeys.spec.ts",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 390, height: 844 },
        deviceScaleFactor: 3,
        isMobile: true,
        hasTouch: true,
      },
    },
  ],
});
