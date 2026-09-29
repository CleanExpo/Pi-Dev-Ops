import { expect, test, type Page } from "@playwright/test";
import { collectFailures, signIn, writeReceipt, type CheckResult } from "./live-session";
import { LIVE_SURFACES, type LiveSurface } from "./surfaces";

// WP-06: one Level 1 read journey per register row. Each surface gets its own
// receipt, so one broken page cannot hide behind another's pass.
function landmarkLocator(page: Page, surface: LiveSurface) {
  const mark = surface.landmark;
  return mark.kind === "heading"
    ? page.getByRole("heading", { name: mark.text, exact: true }).first()
    : page.getByTestId(mark.id).first();
}

// A panel still saying "Loading…" after the page has had time to settle never
// got its data. Without this, a page whose client code never ran passes
// checks 1 and 2 — observed on 29 Sept against a dev server whose panels made
// no requests at all.
const SETTLE_MS = 15_000;
const LOADING_TEXT = /^Loading\b.*(…|\.\.\.)$/;

async function stuckLoadingTexts(page: Page): Promise<string[]> {
  const loading = page.getByText(LOADING_TEXT).filter({ visible: true });
  const deadline = Date.now() + SETTLE_MS;
  while (Date.now() < deadline && (await loading.count()) > 0) {
    await page.waitForTimeout(500);
  }
  const texts = await loading.allInnerTexts();
  return texts.map((t) => t.trim()).filter((t) => t.length > 0);
}

// The dashboard's proxy answers 200 when the backend is down, and each panel
// then shows its own outage text. Check 2 cannot see that, so check 1 reads
// the page. Wording taken from the panels' source on 29 Sept (grep for
// "unreachable|unavailable|Could not|NO LIVE SOURCE|Failed to"). Proved against
// a local build with no backend: swarm, health and runs passed check 2 while
// showing "Pi-CEO backend unreachable" / "could not authenticate upstream".
const OUTAGE_TEXT =
  /(backend|server|upstream) unreachable|could not authenticate upstream|NO LIVE SOURCE YET|SOURCE BROKEN|(graph|list|detail|status|telemetry|packets?) unavailable|Activity unavailable|temporarily unavailable|Failed to load|Could not (read|load|reach)/i;

async function outageTexts(page: Page): Promise<string[]> {
  const texts = await page.getByText(OUTAGE_TEXT).filter({ visible: true }).allInnerTexts();
  return [...new Set(texts.map((t) => t.trim().slice(0, 120)).filter((t) => t.length > 0))];
}

for (const surface of LIVE_SURFACES) {
  test(`${surface.id} ${surface.path} renders with no refused requests`, async ({ page, baseURL }) => {
    const origin = new URL(baseURL ?? "").origin;
    await signIn(page.request);
    const failures = collectFailures(page, origin);

    const nav = await page.goto(surface.path);
    await page.waitForLoadState("networkidle");

    const checks: CheckResult[] = [];
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

    writeReceipt(`${surface.id}${surface.path.replaceAll("/", "_")}`, origin, checks);
    expect(checks.filter((c) => c.result === "FAIL")).toEqual([]);
  });
}
