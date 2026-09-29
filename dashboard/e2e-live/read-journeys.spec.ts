import { expect, test, type Page } from "@playwright/test";
import { landmarkLocator, outageTexts, settle, SETTLE_MS, stuckLoadingTexts } from "./page-state";
import { collectFailures, receiptName, signIn, writeReceipt, type CheckResult, type FailedRequest } from "./live-session";
import { LIVE_SURFACES, type LiveSurface } from "./surfaces";

// WP-06: one Level 1 read journey per register row. Each surface gets its own
// receipt, so one broken page cannot hide behind another's pass. It runs in
// both config projects, desktop and phone, which is MC check 9 (WP-09).
async function runChecks(page: Page, surface: LiveSurface, checks: CheckResult[], failures: FailedRequest[]): Promise<void> {
  const nav = await page.goto(surface.path);
  await settle(page);

  const landed = new URL(page.url()).pathname;
  checks.push({
    check: "1-stayed-on-page",
    result: landed === surface.path && (nav?.status() ?? 0) < 400 ? "PASS" : "FAIL",
    detail: `HTTP ${nav?.status() ?? "none"}, landed on ${landed}`,
  });

  const landmarkShown = await landmarkLocator(page, surface).isVisible();
  const errorPage = await page.getByText("Application Error", { exact: true }).isVisible();
  checks.push({
    check: "1-landmark",
    result: landmarkShown && !errorPage ? "PASS" : "FAIL",
    detail: errorPage ? "app error boundary shown" : `landmark ${JSON.stringify(surface.landmark)} ${landmarkShown ? "visible" : "missing"}`,
  });

  const stuck = await stuckLoadingTexts(page);
  checks.push({
    check: "1-settled",
    result: stuck.length === 0 ? "PASS" : "FAIL",
    detail: stuck.length === 0 ? "no loading text left" : `still loading after ${SETTLE_MS} ms: ${stuck.join(" | ")}`,
  });

  const outages = await outageTexts(page);
  checks.push({
    check: "1-no-outage-shown",
    result: outages.length === 0 ? "PASS" : "FAIL",
    detail: outages.length === 0 ? "no outage text visible" : outages.join(" | "),
  });

  checks.push({
    check: "2-no-hidden-refusals",
    result: failures.length === 0 ? "PASS" : "FAIL",
    detail: failures.length === 0 ? "0 failed requests" : JSON.stringify(failures),
  });
}

// A navigation or wait that throws still leaves a receipt naming the error,
// so a crashed page is never a missing record.
for (const surface of LIVE_SURFACES) {
  test(`${surface.id} ${surface.path} renders with no refused requests`, async ({ page, baseURL }, testInfo) => {
    const origin = new URL(baseURL ?? "").origin;
    const checks: CheckResult[] = [];
    try {
      await signIn(page.request);
      const failures = collectFailures(page, origin);
      await runChecks(page, surface, checks, failures);
    } catch (err) {
      checks.push({ check: "0-journey-completed", result: "FAIL", detail: String(err).slice(0, 500) });
    } finally {
      writeReceipt(receiptName(surface, testInfo.project.name), origin, checks);
    }
    expect(checks.filter((c) => c.result === "FAIL")).toEqual([]);
  });
}
