import { defineConfig, devices } from "@playwright/test";

// Write-action journeys on a LOCAL stack (AAA check 12): the real dashboard
// build against a recording stand-in backend (e2e-writes/fake-backend.mjs).
// Nothing here can reach production: the dashboard is pointed at 127.0.0.1.
// Check 3 (writes survive a reload on a PR preview) is a different suite.
const HOST = "127.0.0.1";
const PORT = Number(process.env.WRITES_PORT ?? 3011);
const BACKEND_PORT = Number(process.env.FAKE_BACKEND_PORT ?? 7778);

export default defineConfig({
  testDir: "./e2e-writes",
  testMatch: "**/*.spec.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  // Its own folder: Playwright empties outputDir when a run starts, and the
  // default (test-results) is where the live suite leaves its failure traces.
  outputDir: "./test-results-writes",
  expect: { timeout: 15_000 },
  retries: 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: `http://${HOST}:${PORT}`,
    viewport: { width: 1280, height: 900 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
  },
  webServer: [
    {
      command: "node e2e-writes/fake-backend.mjs",
      url: `http://${HOST}:${BACKEND_PORT}/__calls`,
      reuseExistingServer: false,
      timeout: 30_000,
      env: { ...process.env, FAKE_BACKEND_PORT: String(BACKEND_PORT) },
    },
    {
      // WRITES_DEV=1 serves source with `next dev`, so a deliberate break of a
      // button can be tried without a rebuild. CI always uses the built app.
      command: `npx next ${process.env.WRITES_DEV ? "dev" : "start"} --port ${PORT} --hostname ${HOST}`,
      url: `http://${HOST}:${PORT}`,
      reuseExistingServer: false,
      timeout: 180_000,
      env: {
        ...process.env,
        DASHBOARD_PASSWORD: "dev",
        PI_CEO_URL: `http://${HOST}:${BACKEND_PORT}`,
        RAILWAY_URL: `http://${HOST}:${BACKEND_PORT}`,
        PI_CEO_PASSWORD: "writes-suite-stub",
        NEXT_PUBLIC_SUPABASE_URL: "https://stub.supabase.co",
        NEXT_PUBLIC_SUPABASE_ANON_KEY: "stub-key",
        NEXT_TELEMETRY_DISABLED: "1",
      },
    },
  ],
});
