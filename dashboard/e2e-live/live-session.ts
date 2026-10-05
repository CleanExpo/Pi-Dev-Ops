import fs from "node:fs";
import path from "node:path";
import type { APIRequestContext, Page, Response } from "@playwright/test";

export interface CheckResult {
  check: string;
  // N/A: the check cannot apply to this page (e.g. a page that makes no
  // browser data requests has no failure path to exercise). Never a pass.
  result: "PASS" | "FAIL" | "N/A";
  detail: string;
}

export interface FailedRequest {
  url: string;
  status: number;
}

// Sign in through the real login route (app/api/auth/login/route.ts). A wrong
// password still answers 200 with {ok:false}, so success is the body flag,
// never the status code.
export async function signIn(request: APIRequestContext): Promise<void> {
  const password = process.env.DASHBOARD_PASSWORD;
  if (!password) {
    throw new Error("DASHBOARD_PASSWORD is not set (RA-7832); the live suite cannot sign in");
  }
  const res = await request.post("/api/auth/login", { data: { password } });
  const body = (await res.json().catch(() => ({}))) as { ok?: boolean; devMode?: boolean };
  if (res.status() !== 200 || body.ok !== true) {
    throw new Error(`Sign-in refused: HTTP ${res.status()}, ok=${String(body.ok)}`);
  }
  if (body.devMode) {
    throw new Error("Target is in dev-password mode; it is not a configured deployment");
  }
}

// MC check 2: collect every same-origin response that fails, so a page that
// looks fine while its data calls are refused cannot pass.
export function collectFailures(page: Page, origin: string): FailedRequest[] {
  const failures: FailedRequest[] = [];
  page.on("response", (res: Response) => {
    if (res.url().startsWith(origin) && res.status() >= 400) {
      failures.push({ url: res.url(), status: res.status() });
    }
  });
  return failures;
}

// MC check 4: every run leaves a receipt naming what was tested and when.
export function writeReceipt(name: string, target: string, checks: CheckResult[]): string {
  const dir = path.join(process.cwd(), "e2e-live-receipts");
  fs.mkdirSync(dir, { recursive: true });
  const file = path.join(dir, `${name}.json`);
  const receipt = {
    surface: name,
    target,
    deployed_sha: process.env.MC_LIVE_SHA ?? null,
    run_at: new Date().toISOString(),
    checks,
  };
  fs.writeFileSync(file, `${JSON.stringify(receipt, null, 2)}\n`);
  return file;
}

// One receipt per surface per viewport, so the phone run (check 9) never
// overwrites the desktop one. Desktop keeps its WP-06 name unchanged.
export function receiptName(surface: { id: string; path: string }, project: string, kind = ""): string {
  const base = `${surface.id}${surface.path.replaceAll("/", "_")}${kind}`;
  return project === "desktop" || project === "" ? base : `${base}@${project}`;
}
