// @vitest-environment jsdom
/**
 * Every field on a project card says what is known: a value, a genuine empty,
 * or UNAVAILABLE with the reason. A failed read never renders as 0 or "passing".
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import ProjectCardTruth from "@/components/control/ProjectCardTruth";
import type { RepoTruth } from "@/lib/control/card-truth";

afterEach(cleanup);

const NOW = Date.parse("2026-10-22T12:00:00Z");
const okTruth: RepoTruth = {
  repo: "CleanExpo/carsi", checked_at: "2026-10-22T12:00:00Z",
  pull_requests: { status: "ok", value: { count: 0, capped: false } },
  ci: { status: "ok", value: { branch: "main", sha: "abc1234def", state: "failure" } },
};

function show(props: Partial<Parameters<typeof ProjectCardTruth>[0]> = {}) {
  render(<ProjectCardTruth truth={okTruth} finishedAt={null} deployments={{}} deployCheck={null} nowMs={NOW} {...props} />);
}

describe("ProjectCardTruth", () => {
  it("EMPTY: a good read of no PRs says 0 open PRs", () => {
    show();
    expect(screen.getByText("0 open PRs")).toBeTruthy();
  });

  it("LOADED: shows CI state on the default branch", () => {
    show();
    expect(screen.getByText("CI main: failing")).toBeTruthy();
  });

  it("caps the count honestly when GitHub returned a full page", () => {
    show({ truth: { ...okTruth, pull_requests: { status: "ok", value: { count: 30, capped: true } } } });
    expect(screen.getByText("30+ open PRs")).toBeTruthy();
  });

  it("ERROR: failed PR and CI reads render UNAVAILABLE with the reason, never 0", () => {
    show({ truth: { ...okTruth, pull_requests: { status: "unavailable", reason: "GitHub pulls HTTP 502" },
      ci: { status: "unavailable", reason: "GITHUB_TOKEN not set" } } });
    expect(screen.getByText("PRs UNAVAILABLE: GitHub pulls HTTP 502")).toBeTruthy();
    expect(screen.getByText("CI UNAVAILABLE: GITHUB_TOKEN not set")).toBeTruthy();
    expect(screen.queryByText(/open PRs/)).toBeNull();
  });

  it("LOADING: says checking, not a value", () => {
    show({ truth: null });
    expect(screen.getByText("PRs checking…")).toBeTruthy();
  });

  it("dates the scan, and says unknown when the scan is undated", () => {
    show({ finishedAt: "2026-10-22T09:00:00Z" });
    expect(screen.getByText("scanned 3h ago")).toBeTruthy();
    cleanup();
    show({ finishedAt: null });
    expect(screen.getByText("scan date unknown")).toBeTruthy();
  });

  it("deploy: not tracked when the registry holds no deploy URL", () => {
    show();
    expect(screen.getByText("deploy: not tracked")).toBeTruthy();
  });

  it("deploy: names the URL and says status not recorded when no check exists", () => {
    show({ deployments: { frontend: "https://carsi.example" } });
    expect(screen.getByText("deploy https://carsi.example · status not recorded")).toBeTruthy();
  });

  it("deploy: shows the last recorded check and its age", () => {
    show({ deployments: { frontend: "https://carsi.example" },
      deployCheck: { finished_at: "2026-10-21T12:00:00Z", error: "", findings: [] } });
    expect(screen.getByText("deploy https://carsi.example · responding at last check 1d ago")).toBeTruthy();
    cleanup();
    show({ deployments: { frontend: "https://carsi.example" },
      deployCheck: { finished_at: "2026-10-21T12:00:00Z", error: "", findings: [{ severity: "critical", title: "Deployment 5xx: frontend" }] } });
    expect(screen.getByText("deploy https://carsi.example · Deployment 5xx: frontend (1d ago)")).toBeTruthy();
  });

  it("deploy: a failed check renders UNAVAILABLE with the reason", () => {
    show({ deployments: { frontend: "https://carsi.example" },
      deployCheck: { finished_at: null, error: "deploy check record unreadable", findings: [] } });
    expect(screen.getByText("deploy UNAVAILABLE: deploy check record unreadable")).toBeTruthy();
  });
});
