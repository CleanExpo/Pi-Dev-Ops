import { expect, test } from "@playwright/test";
import { checkAccessibility, checkAuthBoundary, checkFailurePath, recordDataCalls } from "./level2-checks";
import { receiptName, signIn, writeReceipt, type CheckResult } from "./live-session";
import { stuckLoadingTexts } from "./page-state";
import { LIVE_SURFACES } from "./surfaces";

// WP-09: Level 2 checks 5, 6 and 8 per register row, one receipt per surface
// ("-L2" suffix, beside the WP-06 read-journey receipt). Order matters: the
// normal signed-in visit first (axe scan, and it records the data calls check 6
// replays signed-out), then the forced outage, which re-navigates.
for (const surface of LIVE_SURFACES) {
  test(`${surface.id} ${surface.path} fails honestly, guards auth, passes axe`, async (
    { page, baseURL, playwright },
    testInfo,
  ) => {
    test.setTimeout(180_000);
    const origin = new URL(baseURL ?? "").origin;
    const checks: CheckResult[] = [];
    const anon = await playwright.request.newContext({ baseURL: origin });
    try {
      await signIn(page.request);
      const dataCalls = recordDataCalls(page, origin);
      await page.goto(surface.path);
      await page.waitForLoadState("networkidle");
      await stuckLoadingTexts(page);
      checks.push(await checkAccessibility(page));
      checks.push(await checkAuthBoundary(anon, surface, dataCalls));
      checks.push(await checkFailurePath(page, surface, origin));
    } catch (err) {
      checks.push({ check: "0-journey-completed", result: "FAIL", detail: String(err).slice(0, 500) });
    } finally {
      await anon.dispose();
      writeReceipt(receiptName(surface, testInfo.project.name, "-L2"), origin, checks);
    }
    expect(checks.filter((c) => c.result === "FAIL")).toEqual([]);
  });
}
