import { expect, test } from "@playwright/test";
import { CONTROL_NAV } from "../lib/control/nav";
import { collectFailures, signIn, writeReceipt, type CheckResult } from "./live-session";

// Register row MC-00 / promise P01: the signed-in hub renders its real
// navigation, and nothing the page asks for is refused.
test("Mission Control hub renders for a signed-in user with no refused requests", async ({
  page,
  baseURL,
}) => {
  const origin = new URL(baseURL ?? "").origin;
  await signIn(page.request);
  const failures = collectFailures(page, origin);

  await page.goto("/control");
  await page.waitForLoadState("networkidle");

  const checks: CheckResult[] = [];
  const onControl = new URL(page.url()).pathname.startsWith("/control");
  checks.push({
    check: "1-signed-in-hub",
    result: onControl ? "PASS" : "FAIL",
    detail: `landed on ${page.url()}`,
  });

  const missing: string[] = [];
  for (const item of CONTROL_NAV) {
    const visible = await page.getByText(item.label, { exact: true }).first().isVisible();
    if (!visible) missing.push(item.label);
  }
  checks.push({
    check: "1-nav-labels",
    result: missing.length === 0 ? "PASS" : "FAIL",
    detail: missing.length === 0 ? `${CONTROL_NAV.length} labels visible` : `missing: ${missing.join(", ")}`,
  });

  checks.push({
    check: "2-no-hidden-refusals",
    result: failures.length === 0 ? "PASS" : "FAIL",
    detail: failures.length === 0 ? "0 failed requests" : JSON.stringify(failures),
  });

  writeReceipt("control-hub", origin, checks);
  expect(checks.filter((c) => c.result === "FAIL")).toEqual([]);
});
