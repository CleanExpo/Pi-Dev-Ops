// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import PortfolioFocus, { observedScanScore } from "@/components/control/PortfolioFocus";
import { fetchProxyJSON } from "@/lib/pi-ceo-fetch";

vi.mock("@/lib/pi-ceo-fetch", () => ({ fetchProxyJSON: vi.fn() }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });

it("checks 1,000 varied scan states before showing a measured score", () => {
  for (let index = 0; index < 1000; index++) {
    const value = index % 101;
    const hasScan = index % 3 !== 0;
    const project = {
      project_id: `Project${index}`,
      repo: `CleanExpo/Project${index}`,
      overall_health: hasScan ? value : 100,
      scores: hasScan ? { [index % 2 ? "security" : "quality"]: value } : {},
    };
    expect(observedScanScore(project)).toBe(hasScan ? value : null);
  }
});

it("LOADED: separates scan health, observed work, and unverified release stages when switching projects", async () => {
  vi.mocked(fetchProxyJSON).mockImplementation(async (path) => path === "/api/projects/health"
    ? [
        { project_id: "RestoreAssist", repo: "CleanExpo/RestoreAssist", overall_health: 82, scores: { security: 82 }, findings_count: {}, deployments: {} },
        { project_id: "CARSI", repo: "CleanExpo/CARSI", overall_health: 61, scores: { security: 61 }, findings_count: {}, deployments: {} },
      ] as never
    : path === "/api/pipelines" ? [] as never
    : { ts: new Date().toISOString(), throughput: { hourly: [] }, recent_completions: [], queue: { urgent: 0, high: 0 }, pulse: {}, active_sessions: [{ id: "run-1", repo: "CleanExpo/CARSI", phase: "building", issue_id: "CARSI-1" }] } as never);
  render(<PortfolioFocus />);
  await waitFor(() => expect(screen.getByRole("button", { name: /CARSI, work observed/ })).toBeTruthy());
  fireEvent.click(screen.getByRole("button", { name: /CARSI, work observed/ }));
  expect(screen.getByRole("button", { name: /CARSI, work observed/ }).getAttribute("aria-pressed")).toBe("true");
  expect(screen.getByText(/CARSI-1/)).toBeTruthy();
  expect(screen.getByText("Code scans · not release progress")).toBeTruthy();
  expect(screen.getByText(/Pathway status unknown/)).toBeTruthy();
  expect(screen.getAllByText("unverified")).toHaveLength(8);
});

it("ERROR: fails closed when the project source cannot be read", async () => {
  vi.mocked(fetchProxyJSON).mockResolvedValue(null);
  render(<PortfolioFocus />);
  await waitFor(() => expect(screen.getByText(/Portfolio source unavailable/)).toBeTruthy());
  expect(screen.queryByText(/SCAN HEALTH/)).toBeNull();
});

it("EMPTY: an empty project list says the source returned none, not that it is unavailable", async () => {
  vi.mocked(fetchProxyJSON).mockImplementation(async (path) => path === "/api/projects/health" ? [] as never
    : path === "/api/pipelines" ? [] as never : { ts: new Date().toISOString(), throughput: { hourly: [] }, recent_completions: [], queue: { urgent: 0, high: 0 }, pulse: {}, active_sessions: [] } as never);
  render(<PortfolioFocus />);
  await waitFor(() => expect(screen.getByText("No projects returned by the project health source.")).toBeTruthy());
  expect(screen.queryByText(/Portfolio source unavailable/)).toBeNull();
});

it("ERROR: labels activity unknown when the live feed fails instead of claiming no active work", async () => {
  vi.mocked(fetchProxyJSON).mockImplementation(async (path) => path === "/api/projects/health"
    ? [{ project_id: "CARSI", repo: "CleanExpo/CARSI", overall_health: 100, scores: {}, findings_count: {}, deployments: {} }] as never
    : null);
  render(<PortfolioFocus />);
  await waitFor(() => expect(screen.getByRole("button", { name: /CARSI, activity unknown/ })).toBeTruthy());
  expect(screen.getByText(/Activity source unavailable/)).toBeTruthy();
  expect(screen.queryByText("NO ACTIVE WORK")).toBeNull();
});

it("does not present the scanner's default 100 as a measured score when no scans exist", async () => {
  vi.mocked(fetchProxyJSON).mockImplementation(async (path) => path === "/api/projects/health"
    ? [{ project_id: "CARSI", repo: "CleanExpo/CARSI", overall_health: 100, scores: {}, findings_count: {}, deployments: {} }] as never
    : path === "/api/pipelines" ? [] as never
    : { ts: new Date().toISOString(), throughput: { hourly: [] }, recent_completions: [], queue: { urgent: 0, high: 0 }, pulse: {}, active_sessions: [] } as never);
  render(<PortfolioFocus />);
  await waitFor(() => expect(screen.getByRole("button", { name: /CARSI, no active work observed/ })).toBeTruthy());
  expect(screen.getByText("SCAN HEALTH UNKNOWN")).toBeTruthy();
  expect(screen.getByText("No scan evidence")).toBeTruthy();
  expect(screen.queryByText("100/100")).toBeNull();
});

it("shows completed stages only for a pipeline tied to the selected repository", async () => {
  vi.mocked(fetchProxyJSON).mockImplementation(async (path) => path === "/api/projects/health"
    ? [{ project_id: "CARSI", repo: "CleanExpo/CARSI", overall_health: 61, scores: { security: 61 }, findings_count: {}, deployments: {} }] as never
    : path === "/api/pipelines"
      ? [{ pipeline_id: "CARSI-14", repo_url: "https://github.com/CleanExpo/CARSI.git", current_phase: "test", phases_completed: ["spec", "plan"], updated_at: "2026-09-29T12:00:00Z" }] as never
      : { ts: new Date().toISOString(), throughput: { hourly: [] }, recent_completions: [], queue: { urgent: 0, high: 0 }, pulse: {}, active_sessions: [] } as never);
  render(<PortfolioFocus />);
  await waitFor(() => expect(screen.getByText(/Latest matched pipeline CARSI-14/)).toBeTruthy());
  expect(screen.getAllByText("completed")).toHaveLength(2);
  expect(screen.getAllByText("unverified")).toHaveLength(5);
  expect(screen.getByText("pipeline recorded")).toBeTruthy();
});

it("shows five founder answers with linked evidence and an honest shipped unknown", async () => {
  vi.mocked(fetchProxyJSON).mockImplementation(async (path) => path === "/api/projects/health"
    ? [{ project_id: "RestoreAssist", repo: "CleanExpo/RestoreAssist", overall_health: 100, scores: {}, findings_count: {}, deployments: {} }] as never
    : path === "/api/pipelines" ? [] as never
    : { ts: new Date().toISOString(), throughput: { hourly: [] }, recent_completions: [], pulse: {}, active_sessions: [], queue: { urgent: 0, high: 0, next_issue_id: "RA-42", next_issue_title: "Repair dispatch" },
        observability: { actions: [] }, idea_pipeline: { awaiting: 1 } } as never);
  render(<PortfolioFocus><div id="idea-pipeline">Idea inbox</div></PortfolioFocus>);
  await waitFor(() => expect(screen.getByRole("heading", { name: "The founder’s five answers" })).toBeTruthy());
  expect(screen.getByText(/RA-42 · Repair dispatch/)).toBeTruthy();
  expect(screen.getByText(/1 idea awaits disposition/)).toBeTruthy();
  expect(screen.getByRole("link", { name: "Source: Idea pipeline" }).getAttribute("href")).toBe("#idea-pipeline");
  expect(screen.getByText(/This feed records build completions/)).toBeTruthy();
});
