// @vitest-environment jsdom
// PortfolioFocus — `active_sessions: null` means the session store could not
// be read. It must never render as "NO ACTIVE WORK" (review P1, mc-truth-1).
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import PortfolioFocus from "@/components/control/PortfolioFocus";
import { fetchProxyJSON } from "@/lib/pi-ceo-fetch";

vi.mock("@/lib/pi-ceo-fetch", () => ({ fetchProxyJSON: vi.fn() }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });

const PROJECTS = [{ project_id: "pi-dev-ops", repo: "CleanExpo/Pi-Dev-Ops", overall_health: 80, scores: { security: 80 }, findings_count: {}, deployments: {} }];

function mockSources(live: unknown) {
  vi.mocked(fetchProxyJSON).mockImplementation(async (path) => path === "/api/projects/health" ? PROJECTS as never
    : path === "/api/pipelines" ? [] as never : live as never);
}

it("null active_sessions reads as activity unknown, not no active work", async () => {
  mockSources({
    ts: new Date().toISOString(),
    throughput: { hourly: null },
    active_sessions: null,
    recent_completions: null,
    queue: { available: false, error: "Linear rate limited", urgent: null, high: null },
    pulse: { available: false, error: "Linear rate limited" },
  });
  render(<PortfolioFocus />);
  await waitFor(() => expect(screen.getByRole("button", { name: /pi-dev-ops, activity unknown/ })).toBeTruthy());
  expect(screen.queryByText("NO ACTIVE WORK")).toBeNull();
  expect(screen.queryByRole("button", { name: /no active work observed/ })).toBeNull();
  expect(screen.queryByText(/No active session observed/)).toBeNull();
  expect(screen.getByText("UNKNOWN")).toBeTruthy();
  expect(screen.getByText(/Session store unavailable/)).toBeTruthy();
});

it("positive control: a real session still shows as work observed", async () => {
  mockSources({
    ts: new Date().toISOString(),
    throughput: { hourly: [] },
    active_sessions: [{ id: "run-1", repo: "CleanExpo/Pi-Dev-Ops", phase: "building", issue_id: "RA-1" }],
    recent_completions: [],
    queue: { available: true, urgent: 0, high: 0 },
    pulse: { available: true },
  });
  render(<PortfolioFocus />);
  await waitFor(() => expect(screen.getByRole("button", { name: /pi-dev-ops, work observed/ })).toBeTruthy());
  expect(screen.getByText("WORKING")).toBeTruthy();
  expect(screen.getByText(/RA-1/)).toBeTruthy();
});
