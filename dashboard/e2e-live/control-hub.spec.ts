import { expect, test } from "@playwright/test";
import { MISSION_HOME_LINKS } from "../lib/control/mission-home-links";
import { collectFailures, signIn, writeReceipt, type CheckResult } from "./live-session";
import { settle } from "./page-state";

// Register row MC-00 / promise P01: the signed-in hub renders its real
// navigation, and nothing the page asks for is refused. Since #828 the hub's
// navigation is MissionHomeShell's sidebar, not the CONTROL_NAV section list.
test("Mission Control hub renders for a signed-in user with no refused requests", async ({
  page,
  baseURL,
}) => {
  const origin = new URL(baseURL ?? "").origin;
  await signIn(page.request);
  const failures = collectFailures(page, origin);

  await page.goto("/control");
  await settle(page);

  const checks: CheckResult[] = [];
  const onControl = new URL(page.url()).pathname.startsWith("/control");
  checks.push({
    check: "1-signed-in-hub",
    result: onControl ? "PASS" : "FAIL",
    detail: `landed on ${page.url()}`,
  });

  const missing: string[] = [];
  const nav = page.getByRole("navigation", { name: "Mission Control views" });
  for (const item of MISSION_HOME_LINKS) {
    const visible = await nav.getByRole("link", { name: item.label }).first().isVisible();
    if (!visible) missing.push(item.label);
  }
  checks.push({
    check: "1-nav-labels",
    result: missing.length === 0 ? "PASS" : "FAIL",
    detail: missing.length === 0 ? `${MISSION_HOME_LINKS.length} labels visible` : `missing: ${missing.join(", ")}`,
  });

  checks.push({
    check: "2-no-hidden-refusals",
    result: failures.length === 0 ? "PASS" : "FAIL",
    detail: failures.length === 0 ? "0 failed requests" : JSON.stringify(failures),
  });

  writeReceipt("control-hub", origin, checks);
  expect(checks.filter((c) => c.result === "FAIL")).toEqual([]);
});
