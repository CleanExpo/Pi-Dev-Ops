import { defineConfig, devices } from "@playwright/test";

const HOST = "127.0.0.1";
const PORT = Number(process.env.PLACECARDS_PORT ?? 3010);
const isCI = Boolean(process.env.CI);

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.spec.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  retries: 0,
  reporter: isCI ? [["github"], ["list"]] : "list",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: `http://${HOST}:${PORT}`,
    viewport: { width: 1280, height: 900 },
    screenshot: "only-on-failure",
    trace: "on-first-retry",
  },
  webServer: {
    command: isCI
      ? `npx next start --port ${PORT} --hostname ${HOST}`
      : `npx next dev --port ${PORT} --hostname ${HOST}`,
    url: `http://${HOST}:${PORT}`,
    reuseExistingServer: !isCI,
    timeout: 180_000,
    env: {
      ...process.env,
      DASHBOARD_PASSWORD: process.env.DASHBOARD_PASSWORD ?? "dev",
      PI_CEO_URL: process.env.PI_CEO_URL ?? "http://127.0.0.1:7777",
      PI_CEO_PASSWORD: process.env.PI_CEO_PASSWORD ?? "ci-build-stub",
      NEXT_PUBLIC_SUPABASE_URL:
        process.env.NEXT_PUBLIC_SUPABASE_URL ?? "https://stub.supabase.co",
      NEXT_PUBLIC_SUPABASE_ANON_KEY:
        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "stub-key",
      NEXT_TELEMETRY_DISABLED: "1",
    },
  },
});
