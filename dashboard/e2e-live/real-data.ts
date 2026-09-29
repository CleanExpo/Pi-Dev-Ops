import type { Page } from "@playwright/test";
import type { CheckResult } from "./live-session";

// MC check 1 (docs/plans/mission-control/aaa-rating.md): the page shows at least
// one element whose content came from the live backend. Components mark that
// element with data-mc-data="<what>" and render it only in their loaded branch,
// never while loading, on error, or for an empty result. A page whose correct
// state is empty marks its explicit empty copy with data-mc-empty="<why empty
// is correct>". The shell (sidebar, top bar) uses neither attribute, so its
// health light cannot pass a page whose own panels loaded nothing.
async function visibleMarks(page: Page, attr: string): Promise<string[]> {
  const marks = page.locator(`[${attr}]`).filter({ visible: true });
  const count = await marks.count();
  const out: string[] = [];
  for (let i = 0; i < Math.min(count, 3); i += 1) {
    const mark = marks.nth(i);
    const what = (await mark.getAttribute(attr)) ?? "";
    const text = (await mark.innerText()).replace(/\s+/g, " ").trim().slice(0, 60);
    out.push(`${what}: "${text}"`);
  }
  return out;
}

export async function checkRealData(page: Page): Promise<CheckResult> {
  const data = await visibleMarks(page, "data-mc-data");
  if (data.length > 0) {
    return { check: "1-real-data", result: "PASS", detail: data.join(" | ") };
  }
  const empty = await visibleMarks(page, "data-mc-empty");
  if (empty.length > 0) {
    return { check: "1-real-data", result: "PASS", detail: `honest empty state — ${empty.join(" | ")}` };
  }
  return {
    check: "1-real-data",
    result: "FAIL",
    detail: "no element rendered from live data (data-mc-data) or explicit empty state (data-mc-empty)",
  };
}
