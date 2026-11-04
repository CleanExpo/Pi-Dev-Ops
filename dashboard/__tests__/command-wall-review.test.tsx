/**
 * PR #966 review fixes. The PR panel is "live" only when every repo's PRs AND
 * main CI were read; a stale fleet read shows its reason; a first read in
 * flight reads "connecting", never "unavailable"; capped lane counts carry the
 * cap marker; a stalled flow-board read gives up instead of piling up.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PrPipelineScreen from "@/components/control/wall/PrPipelineScreen";
import { WALL_REPOS, fleetFailureText, prPipelineTone, prRow, type PrRow } from "@/lib/control/command-wall";
import { REPO_BOARD_TIMEOUT_MS, readBoard } from "@/lib/control/useRepoBoards";

function readRow(repo: string, over: Partial<PrRow> = {}): PrRow {
  return {
    repo, name: repo.split("/")[1] ?? repo, open: 3, capped: false, auditLane: 1, needsPhill: 1, aging: 0,
    ci: { tone: "ok", text: "passing" }, ciReason: null, reason: null, ...over,
  };
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("PR pipeline panel state", () => {
  it("is not live when a repo's main CI could not be read", () => {
    const rows = WALL_REPOS.map((r, i) => readRow(r, i === 0 ? { ci: { tone: "idle", text: "unavailable" }, ciReason: "GitHub CI HTTP 404" } : {}));
    expect(prPipelineTone(rows)).toEqual({ tone: "warn", text: "5 of 6 repos read" });
  });

  it("is live only when every repo's PRs and CI were read", () => {
    expect(prPipelineTone(WALL_REPOS.map((r) => readRow(r)))).toEqual({ tone: "ok", text: "live" });
  });

  it("reads connecting before the first board read", () => {
    expect(prPipelineTone(WALL_REPOS.map((r) => prRow(r, undefined)))).toEqual({ tone: "idle", text: "connecting" });
  });
});

describe("fleet failure text", () => {
  it("a stale wall read with no snapshot names its reason", () => {
    expect(fleetFailureText("stale", "HTTP 502")).toBe("Fleet stale: HTTP 502");
  });

  it("live and loading reads carry no failure", () => {
    expect(fleetFailureText("live", null)).toBeNull();
    expect(fleetFailureText("loading", null)).toBeNull();
  });
});

describe("first read in flight", () => {
  it("marks CI connecting before a read, unavailable after a failed one", () => {
    expect(prRow("CleanExpo/Synthex", undefined).ci.text).toBe("connecting");
    expect(prRow("CleanExpo/Synthex", null, "flow board HTTP 500").ci.text).toBe("unavailable");
  });

  it("the table never says unavailable while reads are still connecting", () => {
    render(<PrPipelineScreen rows={WALL_REPOS.map((r) => prRow(r, undefined))} />);
    expect(screen.queryByText(/unavailable/)).toBeNull();
    expect(screen.getAllByText("connecting")).toHaveLength(12);
  });
});

describe("capped counts", () => {
  it("lane cells carry the cap marker when the open list was capped", () => {
    render(<PrPipelineScreen rows={[readRow("CleanExpo/Synthex", { open: 30, capped: true, auditLane: 2, needsPhill: 1, aging: 0 })]} />);
    expect(screen.getByText("30+")).toBeTruthy();
    expect(screen.getByText("2+")).toBeTruthy();
    expect(screen.getByText("1+")).toBeTruthy();
    expect(screen.getByText("0+")).toBeTruthy();
  });
});

describe("flow-board read timeout", () => {
  it("a stalled read gives up with a reason instead of hanging", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn((_url: string, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    })));
    const pending = readBoard("CleanExpo/Synthex", new AbortController().signal);
    await vi.advanceTimersByTimeAsync(REPO_BOARD_TIMEOUT_MS);
    await expect(pending).resolves.toEqual({ board: null, reason: "flow board timed out" });
  });
});
