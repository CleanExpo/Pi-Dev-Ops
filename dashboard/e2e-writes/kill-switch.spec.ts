import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { expect, test, type Locator, type Page } from "@playwright/test";

// MC-03 write actions, AAA check 12 (label honesty): for each button, the
// requests the backend actually received match what the label claims. "Halt
// swarm" sends a kill and no resume; "Resume swarm" the reverse; Cancel and an
// invalid form send nothing; a refused halt is shown and does not look halted.
// Each journey also reloads and reads the state back. Local stack, stand-in
// backend (see fake-backend.mjs): this measures what the dashboard sends, not
// whether the real backend accepts it.
const BACKEND = `http://127.0.0.1:${process.env.FAKE_BACKEND_PORT ?? 7778}`;
const EXPECTED = [
  "12-halt-sends-kill-and-only-kill",
  "12-resume-sends-resume-and-only-resume",
  "12-cancel-sends-nothing",
  "12-invalid-halt-sends-nothing",
  "12-refused-halt-is-shown-not-applied",
];

type Call = { method: string; path: string; body: Record<string, unknown> };
type Check = { check: string; result: "PASS" | "FAIL"; detail: string };
const results: Check[] = [];

async function backendCalls(page: Page): Promise<Call[]> {
  return (await page.request.get(`${BACKEND}/__calls`)).json();
}
const only = (all: Call[], suffix: string) => all.filter((c) => c.path === `/api/swarm/${suffix}`);

async function journey(check: string, body: () => Promise<void>): Promise<void> {
  try {
    await body();
    results.push({ check, result: "PASS", detail: "" });
  } catch (error) {
    const first = String(error instanceof Error ? error.message : error).split("\n")[0];
    results.push({ check, result: "FAIL", detail: first.slice(0, 200) });
    throw error;
  }
}

function killSwitch(page: Page): Locator {
  return page.locator("div.rounded.border.p-3", { has: page.getByText("Kill Switch", { exact: true }) });
}

async function fillHalt(page: Page, a1: string, a2: string): Promise<Locator> {
  const dialog = page.getByRole("dialog");
  await dialog.locator("select").nth(0).selectOption(a1);
  await dialog.locator("select").nth(1).selectOption(a2);
  await dialog.getByPlaceholder("123456").nth(0).fill("123456");
  await dialog.getByPlaceholder("123456").nth(1).fill("654321");
  await dialog.getByPlaceholder("incident-12345").fill("e2e-halt");
  return dialog;
}

test.describe.configure({ mode: "serial" });

test.beforeEach(async ({ page }) => {
  await page.request.post(`${BACKEND}/__reset`);
  const login = await page.request.post("/api/auth/login", { data: { password: "dev" } });
  expect(login.ok()).toBeTruthy();
  await page.goto("/control/swarm");
  await expect(killSwitch(page).getByText("RUNNING", { exact: true })).toBeVisible();
});

test.afterAll(() => {
  const seen = new Set(results.map((r) => r.check));
  for (const check of EXPECTED) {
    if (!seen.has(check)) results.push({ check, result: "FAIL", detail: "journey did not run to the end" });
  }
  const dir = path.join(process.cwd(), "e2e-live-receipts");
  mkdirSync(dir, { recursive: true });
  const receipt = { surface: "MC-03-W", run_at: new Date().toISOString(), checks: results };
  writeFileSync(path.join(dir, "MC-03-W.json"), JSON.stringify(receipt, null, 2) + "\n", "utf8");
});

test("Halt swarm sends one kill with what was typed, no resume, and survives a reload", async ({ page }) => {
  await journey("12-halt-sends-kill-and-only-kill", async () => {
    await killSwitch(page).getByRole("button", { name: "Halt swarm" }).click();
    const dialog = await fillHalt(page, "alice", "bob");
    await dialog.getByRole("button", { name: "Halt swarm" }).click();
    await expect(killSwitch(page).getByText("HALTED", { exact: true })).toBeVisible();

    const all = await backendCalls(page);
    expect(only(all, "kill")).toEqual([{
      method: "POST", path: "/api/swarm/kill",
      body: { approver1_user: "alice", approver1_totp: "123456", approver2_user: "bob", approver2_totp: "654321", reason: "e2e-halt" },
    }]);
    expect(only(all, "resume")).toEqual([]);

    await page.reload();
    await expect(killSwitch(page).getByText("HALTED", { exact: true })).toBeVisible();
    await expect(killSwitch(page).getByRole("button", { name: "Resume swarm" })).toBeVisible();
    await expect(killSwitch(page).getByRole("button", { name: "Halt swarm" })).toHaveCount(0);
  });
});

test("Resume swarm sends one resume, no kill, and survives a reload", async ({ page }) => {
  await journey("12-resume-sends-resume-and-only-resume", async () => {
    await page.request.post(`${BACKEND}/__control`, { data: { halted: true } });
    await page.reload();
    await expect(killSwitch(page).getByText("HALTED", { exact: true })).toBeVisible();

    await killSwitch(page).getByRole("button", { name: "Resume swarm" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.locator("select").selectOption("alice");
    await dialog.getByPlaceholder("123456").fill("123456");
    await dialog.getByRole("button", { name: "Resume swarm" }).click();
    await expect(killSwitch(page).getByText("RUNNING", { exact: true })).toBeVisible();

    const all = await backendCalls(page);
    expect(only(all, "resume")).toEqual([{
      method: "POST", path: "/api/swarm/resume",
      body: { approver_user: "alice", approver_totp: "123456", reason: "", confirmed: false },
    }]);
    expect(only(all, "kill")).toEqual([]);

    await page.reload();
    await expect(killSwitch(page).getByText("RUNNING", { exact: true })).toBeVisible();
    await expect(killSwitch(page).getByRole("button", { name: "Halt swarm" })).toBeVisible();
  });
});

test("Cancel on the halt form sends nothing and leaves the swarm running", async ({ page }) => {
  await journey("12-cancel-sends-nothing", async () => {
    await killSwitch(page).getByRole("button", { name: "Halt swarm" }).click();
    const dialog = await fillHalt(page, "alice", "bob");
    await dialog.getByRole("button", { name: "Cancel" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(await backendCalls(page)).toEqual([]);
    await page.reload();
    await expect(killSwitch(page).getByText("RUNNING", { exact: true })).toBeVisible();
  });
});

test("A halt with the same approver twice is refused on the page and sends nothing", async ({ page }) => {
  await journey("12-invalid-halt-sends-nothing", async () => {
    await killSwitch(page).getByRole("button", { name: "Halt swarm" }).click();
    const dialog = await fillHalt(page, "alice", "alice");
    await dialog.getByRole("button", { name: "Halt swarm" }).click();
    await expect(dialog.getByText("approver1 and approver2 must be different non-empty users")).toBeVisible();
    expect(await backendCalls(page)).toEqual([]);
    await expect(killSwitch(page).getByText("HALTED", { exact: true })).toHaveCount(0);
  });
});

test("A halt the backend refuses shows the refusal and never looks halted", async ({ page }) => {
  await journey("12-refused-halt-is-shown-not-applied", async () => {
    await page.request.post(`${BACKEND}/__control`, { data: { failNext: "kill" } });
    await killSwitch(page).getByRole("button", { name: "Halt swarm" }).click();
    const dialog = await fillHalt(page, "alice", "bob");
    await dialog.getByRole("button", { name: "Halt swarm" }).click();
    await expect(dialog.getByText(/approver TOTP rejected/)).toBeVisible();
    await expect(killSwitch(page).getByText("HALTED", { exact: true })).toHaveCount(0);
    expect(only(await backendCalls(page), "kill")).toHaveLength(1);

    await dialog.getByRole("button", { name: "Cancel" }).click();
    await page.reload();
    await expect(killSwitch(page).getByText("RUNNING", { exact: true })).toBeVisible();
    await expect(killSwitch(page).getByRole("button", { name: "Halt swarm" })).toBeVisible();
  });
});
