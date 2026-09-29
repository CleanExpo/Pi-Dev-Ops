import AxeBuilder from "@axe-core/playwright";
import type { APIRequestContext, Page, Request } from "@playwright/test";
import type { CheckResult } from "./live-session";
import { OUTAGE_TEXT, stuckLoadingTexts } from "./page-state";
import type { LiveSurface } from "./surfaces";

// WP-09 (docs/plans/mission-control/work-packages.md): MC checks 5, 6 and 8 as
// defined in docs/plans/mission-control/aaa-rating.md, Level 2. Check 9 (phone
// viewport) is the read journeys re-run by the "phone" project in
// playwright.live.config.ts, not code here.

// A data call the page makes from the browser: same origin, /api/, GET, and not
// the login route (which is public by design, proxy.ts PUBLIC_API_PREFIXES).
function isPageDataCall(url: string, origin: string): boolean {
  const u = new URL(url);
  return u.origin === origin && u.pathname.startsWith("/api/") && !u.pathname.startsWith("/api/auth/");
}

// Records the path+query of every data GET the page makes, for check 6.
export function recordDataCalls(page: Page, origin: string): Set<string> {
  const seen = new Set<string>();
  page.on("request", (req: Request) => {
    if (req.method() === "GET" && isPageDataCall(req.url(), origin)) {
      const u = new URL(req.url());
      seen.add(`${u.pathname}${u.search}`);
    }
  });
  return seen;
}

// Wording a page may use to say its data failed. Broader than the WP-06 outage
// text on purpose: here the outage is forced, so any explicit failure wording
// counts as honest. What must NOT happen is silence, a stuck spinner, or the
// generic app error boundary. "stale" is included because the Wall's designed
// outage state is its "SNAPSHOT STALE — no timestamp" banner (WallBanner.tsx):
// it says outright the data is not current, which is what check 5 asks for.
const FAILURE_TEXT = new RegExp(
  `${OUTAGE_TEXT.source}|\\berror\\b|failed|could not|couldn't|unable to|unavailable|unreachable|offline|stale|try again|retry`,
  "i",
);

// Data calls made by the shell around every page, not by the page itself.
// Cutting only these tests the shell, so a page that makes no other browser
// call has no failure path of its own (it renders on the server) -> N/A.
// Sources, re-checked 29 Sept: CeoHealthPanel + SwarmStatus in
// app/(main)/layout.tsx (/health); TopBar (/api/zte) and its ProjectSelector
// (/api/projects/health); ActiveBuildStrip (/api/sessions).
const SHELL_DATA_CALLS = new Set([
  "/api/pi-ceo/health",
  "/api/zte",
  "/api/pi-ceo/api/projects/health",
  "/api/pi-ceo/api/sessions",
]);

// MC check 5: every browser data call is refused at the network layer, then the
// page must say so explicitly and must not be left "Loading…".
export async function checkFailurePath(page: Page, surface: LiveSurface, origin: string): Promise<CheckResult> {
  const cut = new Set<string>();
  await page.route(
    (url) => isPageDataCall(url.href, origin),
    async (route) => {
      cut.add(new URL(route.request().url()).pathname);
      await route.abort("connectionrefused");
    },
  );
  await page.goto(surface.path);
  await page.waitForLoadState("networkidle").catch(() => undefined);
  const stuck = await stuckLoadingTexts(page);
  await page.unroute(() => true);
  const blocked = [...cut].sort().join(", ");
  const errorBoundary = await page.getByText("Application Error", { exact: true }).isVisible();
  // Only the page's own content counts. The shell's health light and build
  // strip say "Backend unreachable" on every page, which would let a page whose
  // own panels fail silently pass. Found on the first local run, 29 Sept.
  const content = page.locator("[data-mc-page]").last();
  const said = await content.getByText(FAILURE_TEXT).filter({ visible: true }).allInnerTexts();
  const shown = [...new Set(said.map((t) => t.trim().slice(0, 120)).filter((t) => t.length > 0))];
  const scoped = (await content.count()) > 0;
  // N/A only for a page DECLARED server-rendered (surfaces.ts) whose cut calls
  // were all the shell's and which stayed quiet. A path match alone is not
  // enough: MC-05 and MC-06 call /api/sessions themselves, the same path as the
  // shell, so a silent failure there must FAIL, not pass as N/A.
  const quiet = scoped && shown.length === 0 && stuck.length === 0 && !errorBoundary;
  if (surface.serverRendered && quiet && [...cut].every((p) => SHELL_DATA_CALLS.has(p))) {
    const note = cut.size === 0 ? "no browser data calls" : `only shell calls (${blocked})`;
    return { check: "5-failure-path", result: "N/A", detail: `${note}; page data is server-rendered` };
  }
  const pass = scoped && stuck.length === 0 && shown.length > 0 && !errorBoundary;
  const why = !scoped
    ? "no [data-mc-page] content region found"
    : errorBoundary
    ? "generic app error boundary shown"
    : stuck.length > 0
      ? `still loading: ${stuck.join(" | ")}`
      : shown.length === 0
        ? "page content shows no error text (shell status aside)"
        : `says: ${shown.slice(0, 3).join(" | ")}`;
  return { check: "5-failure-path", result: pass ? "PASS" : "FAIL", detail: `cut ${blocked}; ${why}` };
}

// MC check 6: signed out, the page redirects to login and every data call the
// signed-in page made answers 401. `anon` must carry no session cookie.
export async function checkAuthBoundary(
  anon: APIRequestContext,
  surface: LiveSurface,
  dataCalls: Set<string>,
  origin: string,
): Promise<CheckResult> {
  const problems: string[] = [];
  const page = await anon.get(surface.path, { maxRedirects: 0 });
  const location = page.headers()["location"] ?? "";
  // Resolved against the dashboard itself, and the origin must match: a 307 to
  // https://elsewhere.example/ is not this dashboard's login page.
  const target = location.length > 0 ? new URL(location, `${origin}${surface.path}`) : null;
  const toLogin = target !== null && target.origin === origin && target.pathname === "/";
  if (page.status() !== 307 || !toLogin) {
    problems.push(`page answered ${page.status()}${location ? ` → ${location}` : ""}, expected 307 to login`);
  }
  for (const path of dataCalls) {
    const res = await anon
      .get(path, { maxRedirects: 0, timeout: 10_000 })
      .catch((err: unknown) => new Error(String(err)));
    const status = res instanceof Error ? `no answer (${res.message.slice(0, 60)})` : res.status();
    if (status !== 401) problems.push(`${path} answered ${status}, expected 401`);
  }
  const counted = `page + ${dataCalls.size} data call${dataCalls.size === 1 ? "" : "s"}`;
  return {
    check: "6-auth-boundary",
    result: problems.length === 0 ? "PASS" : "FAIL",
    detail: problems.length === 0 ? `${counted} refused signed-out` : `${counted}: ${problems.join("; ")}`,
  };
}

// MC check 8: axe at WCAG 2.2 AA, zero serious or critical violations.
export async function checkAccessibility(page: Page): Promise<CheckResult> {
  const { violations } = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const blocking = violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  return {
    check: "8-accessibility",
    result: blocking.length === 0 ? "PASS" : "FAIL",
    detail:
      blocking.length === 0
        ? `0 serious/critical (${violations.length} lesser)`
        : blocking.map((v) => `${v.id} (${v.impact}, ${v.nodes.length} el)`).join("; "),
  };
}
