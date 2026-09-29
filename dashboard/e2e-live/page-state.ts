import type { Page } from "@playwright/test";
import type { LiveSurface } from "./surfaces";

// Page-state readers shared by the read journeys (WP-06, run at both viewports
// for check 9) and the Level 2 checks (WP-09). Moved here unchanged from
// read-journeys.spec.ts so both specs judge "settled" and "outage" identically.
export function landmarkLocator(page: Page, surface: LiveSurface) {
  const mark = surface.landmark;
  return mark.kind === "heading"
    ? page.getByRole("heading", { name: mark.text, exact: true }).first()
    : page.getByTestId(mark.id).first();
}

// Wait for the page to load, then give its first data calls a bounded chance
// to finish. Never wait for "networkidle" without a cap: 16 control panels
// poll or stream, so on the live site the network is never idle and the wait
// ran to the test timeout (run 36527748153, 29 Sept: the hub and MC-07..MC-10
// each burned 90-180 s and the job hit its 20-minute limit after 11 of 58
// tests). Whether data actually arrived is judged by the checks that follow.
export const QUIET_CAP_MS = 10_000;

export async function settle(page: Page): Promise<void> {
  await page.waitForLoadState("load");
  await page.waitForLoadState("networkidle", { timeout: QUIET_CAP_MS }).catch(() => undefined);
}

// A panel still saying "Loading…" after the page has had time to settle never
// got its data. Without this, a page whose client code never ran passes
// checks 1 and 2 — observed on 29 Sept against a dev server whose panels made
// no requests at all.
export const SETTLE_MS = 15_000;
export const LOADING_TEXT = /^Loading\b.*(…|\.\.\.)$/;

export async function stuckLoadingTexts(page: Page): Promise<string[]> {
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
export const OUTAGE_TEXT =
  /(backend|server|upstream) unreachable|could not authenticate upstream|NO LIVE SOURCE YET|SOURCE BROKEN|(graph|list|detail|status|telemetry|packets?) unavailable|Activity unavailable|temporarily unavailable|Failed to load|Could not (read|load|reach)/i;

export async function outageTexts(page: Page): Promise<string[]> {
  const texts = await page.getByText(OUTAGE_TEXT).filter({ visible: true }).allInnerTexts();
  return [...new Set(texts.map((t) => t.trim().slice(0, 120)).filter((t) => t.length > 0))];
}
