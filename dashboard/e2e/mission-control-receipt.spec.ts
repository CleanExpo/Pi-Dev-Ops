import { execFileSync } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import { expect, test } from "@playwright/test";

// A local browser receipt for Jev replay. Every upstream source is synthetic.
test("Mission Control project focus writes a separate advisory snapshot", async ({ page }, testInfo) => {
  const calls: { method: string; path: string; status: number }[] = [];
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("response", (response) => {
    const url = new URL(response.url());
    if (url.pathname.startsWith("/api/pi-ceo/") || url.pathname === "/api/mesh-fleet") {
      calls.push({ method: response.request().method(), path: url.pathname, status: response.status() });
    }
  });
  await page.route("**/api/pi-ceo/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const body = path.endsWith("/api/projects/health") ? [
      { project_id: "RestoreAssist", repo: "CleanExpo/RestoreAssist", overall_health: 100, scores: {} },
      { project_id: "CARSI", repo: "CleanExpo/CARSI", overall_health: 61, scores: { security: 61 } },
    ] : path.endsWith("/api/pipelines") ? [
      { pipeline_id: "CARSI-14", repo_url: "https://github.com/CleanExpo/CARSI.git", current_phase: "test", phases_completed: ["spec", "plan"], updated_at: "2026-09-29T00:00:00Z" },
    ] : path.endsWith("/api/mission-control/live") ? {
      active_sessions: [], recent_completions: [], throughput: { hourly: Array(24).fill(0) },
    } : path.endsWith("/api/idea-pipeline") ? {
      snapshot: { awaiting: 0, packet: null },
    } : {};
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.route("**/api/mesh-fleet", (route) => route.fulfill({ status: 200, contentType: "application/json", body: '{"status":"unavailable"}' }));

  const password = process.env.DASHBOARD_PASSWORD ?? "dev";
  const login = await page.request.post("/api/auth/login", { data: { password } });
  expect(login.ok()).toBeTruthy();
  const focus = page.getByRole("region", { name: "Portfolio focus" });
  let failure: string | undefined;
  try {
    await page.goto("/control");
    await expect(page.getByRole("button", { name: /RestoreAssist, no active work observed/ })).toBeVisible();
    await expect(focus.getByText("SCAN HEALTH UNKNOWN")).toBeVisible();
    await expect(focus.getByText("No scan evidence")).toBeVisible();
    await page.getByRole("button", { name: /CARSI, no active work observed/ }).click();
    await expect(page.getByRole("button", { name: /CARSI, no active work observed/ })).toHaveAttribute("aria-pressed", "true");
    await expect(focus.getByText("61/100").last()).toBeVisible();
    await expect(focus.getByText(/Latest matched pipeline CARSI-14/)).toBeVisible();
    expect(calls.filter((call) => call.status >= 400)).toEqual([]);
    expect(pageErrors).toEqual([]);
    if (process.env.MISSION_CONTROL_INJECT_FAILURE === "1") {
      throw new Error("Synthetic injected failure for receipt verification");
    }
  } catch (error) {
    failure = error instanceof Error ? error.message.slice(0, 4000) : "Browser assertion failed";
    throw error;
  } finally {
    const sha = process.env.MISSION_CONTROL_SHA ?? execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim();
    const workspaceDirty = Boolean(execFileSync("git", ["status", "--porcelain"], { encoding: "utf8" }).trim());
    const receipt = {
      run_id: `local-${Date.now()}-${testInfo.workerIndex}`,
      sha,
      workspace_dirty: workspaceDirty,
      surface: "/control",
      visible_text: (await focus.innerText().catch(() => "Portfolio unavailable")).slice(0, 24_000),
      network_calls: calls,
      assertions: ["Unscanned project is unknown", "Project selection updates", "Matched pathway is visible", "No failed API responses", "No page errors"],
      data_classification: "synthetic",
      ...(failure ? { failure } : {}),
    };
    const path = process.env.MISSION_CONTROL_RECEIPT_PATH ?? testInfo.outputPath("mission-control-snapshot.jsonl");
    await mkdir(dirname(path), { recursive: true, mode: 0o700 });
    await writeFile(path, `${JSON.stringify(receipt)}\n`, { mode: 0o600 });
    await testInfo.attach("mission-control-snapshot", { path, contentType: "application/x-ndjson" });
  }
});
