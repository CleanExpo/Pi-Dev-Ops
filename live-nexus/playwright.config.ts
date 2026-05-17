import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  use: { baseURL: "http://localhost:3030", trace: "on-first-retry" },
  webServer: {
    command: "pnpm dev --port 3030",
    url: "http://localhost:3030",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    env: {
      ASSEMBLYAI_API_KEY: "fake_key_for_e2e",
      ANTHROPIC_API_KEY: "fake_key_for_e2e",
      DRIVE_SERVICE_ACCOUNT_JSON: "{}",
      DRIVE_FOLDER_ID: "fake_folder",
    },
  },
});
