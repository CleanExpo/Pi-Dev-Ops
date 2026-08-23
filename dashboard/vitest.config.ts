/// <reference types="vitest" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    // Vitest's DEFAULT timeouts are 5s/10s, which this suite silently inherited.
    // They are not survivable here, and the way they fail is worse than slow: the
    // first test in a file pays the whole cold `await import()` of a Next route
    // module inside its own budget, so the timeout lands on whichever assertion
    // happens to be first and is reported as that assertion failing.
    //
    // Measured on the definition-of-done runner, where `scripts/handoff-loop.sh`
    // clears caches and then runs the Python suites immediately before this one,
    // so the dashboard suite always starts cold:
    //   telegram-webhook-auth.test.ts, first test: 6635ms and 7851ms on two runs,
    //   both reported as "REFUSES a request that omits the secret header" FAILING.
    // That reads as "the webhook accepted an unauthenticated request" — a security
    // finding that did not happen. The same class hit session-verifier-single-source
    // and unite-group-server on other runs. Warm, every test in this suite is <100ms.
    //
    // 30s is ~4x the worst observed cold import, so a genuine hang is still caught.
    // Nothing here relaxes an assertion: the same statuses are still required.
    testTimeout: 30_000,
    hookTimeout: 30_000,
    // The suite runs from an external-volume worktree. Unbounded cold fork startup
    // can saturate that volume and time out workers before any test is collected.
    // Two workers preserve file isolation and every assertion while keeping startup bounded.
    maxWorkers: 2,
    include: ["**/__tests__/**/*.{test,spec}.{ts,tsx}", "**/*.{test,spec}.{ts,tsx}"],
    exclude: ["node_modules", ".next"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
});
