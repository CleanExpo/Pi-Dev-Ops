/**
 * SpecPipelinePanel — loaded / empty / error states, the detail poll for a
 * selected pipeline, and the exact proxy paths it requests. The detail path
 * was once 403'd by the /api/pi-ceo allowlist, so every requested path is
 * checked against allowed().
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SpecPipelinePanel from "@/components/control/SpecPipelinePanel";
import { allowed } from "@/lib/pi-ceo-proxy-allowlist";

const PREFIX = "/api/pi-ceo";
const LIST = `${PREFIX}/api/spec-pipeline?limit=10`;

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  cleanup();
});

function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

type Handler = (url: string, init?: RequestInit) => Response | Promise<Response>;

function stubFetch(handler: Handler): string[] {
  const urls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      urls.push(url);
      return handler(url, init);
    }),
  );
  return urls;
}

const PIPELINES = {
  pipelines: [
    { pipeline_id: "spec-abc123", status: "running", proposal: "Add a margot packet viewer" },
    { pipeline_id: "spec-def456", status: "blocked", proposal: "Rewrite auth" },
  ],
};

const DETAIL = {
  meta: {
    pipeline_id: "spec-abc123",
    status: "running",
    judge_score: 81,
    stages: [
      { stage: "validate", status: "pass" },
      { stage: "judge", status: "pass", score: 81, decision: "APPROVE" },
    ],
  },
  running: "running",
  handoff: false,
};

describe("SpecPipelinePanel", () => {
  it("LOADED: renders pipelines from the list endpoint", async () => {
    const urls = stubFetch(() => jsonResponse(PIPELINES));
    render(<SpecPipelinePanel />);
    expect(await screen.findByText("spec-abc123")).toBeTruthy();
    expect(screen.getByText(/Add a margot packet viewer/)).toBeTruthy();
    expect(urls).toEqual([LIST]);
  });

  it("EMPTY: an empty list says so explicitly", async () => {
    stubFetch(() => jsonResponse({ pipelines: [] }));
    render(<SpecPipelinePanel />);
    expect(await screen.findByText("No pipelines yet.")).toBeTruthy();
  });

  it.each([
    [500, "HTTP 500"],
    [403, "HTTP 403"],
  ])("ERROR: list %i is visible, not a silent empty list", async (status, text) => {
    stubFetch(() => jsonResponse({ detail: "nope" }, status));
    render(<SpecPipelinePanel />);
    expect(await screen.findByText(`Pipeline list unavailable — ${text}`)).toBeTruthy();
    expect(screen.queryByText("No pipelines yet.")).toBeNull();
  });

  it("ERROR: a rejected fetch is visible", async () => {
    stubFetch(() => {
      throw new Error("network down");
    });
    render(<SpecPipelinePanel />);
    expect(await screen.findByText(/Pipeline list unavailable — network error/)).toBeTruthy();
  });

  it("ERROR: a proxy placeholder (X-Upstream-Status) reads as unreachable, not empty", async () => {
    stubFetch(() => jsonResponse({ pipelines: [] }, 200, { "X-Upstream-Status": "502" }));
    render(<SpecPipelinePanel />);
    expect(await screen.findByText(/Pipeline list unavailable — Pi-CEO backend unreachable/)).toBeTruthy();
    expect(screen.queryByText("No pipelines yet.")).toBeNull();
  });

  it("selecting a pipeline polls /api/spec-pipeline/<id> and shows detail", async () => {
    const setIntervalSpy = vi.spyOn(globalThis, "setInterval");
    const urls = stubFetch((url) =>
      url.startsWith(`${PREFIX}/api/spec-pipeline/spec-abc123`) ? jsonResponse(DETAIL) : jsonResponse(PIPELINES),
    );
    render(<SpecPipelinePanel />);
    fireEvent.click(await screen.findByText("spec-abc123"));

    const detailUrl = `${PREFIX}/api/spec-pipeline/spec-abc123`;
    expect(await screen.findByText("judge · pass · 81 · APPROVE")).toBeTruthy();
    expect(screen.getByText(/\(judge 81\)/)).toBeTruthy();
    expect(urls.filter((u) => u === detailUrl)).toHaveLength(1);

    // The panel schedules a 4 s poll for the selected pipeline; fire it.
    const poll = setIntervalSpy.mock.calls.find(([, ms]) => ms === 4000);
    expect(poll).toBeTruthy();
    const tick = poll?.[0];
    if (typeof tick === "function") tick();
    await waitFor(() => expect(urls.filter((u) => u === detailUrl)).toHaveLength(2));
  });

  it("ERROR: a failing detail poll is visible after selecting a pipeline", async () => {
    stubFetch((url) =>
      url.startsWith(`${PREFIX}/api/spec-pipeline/spec-abc123`)
        ? jsonResponse({ detail: "boom" }, 500)
        : jsonResponse(PIPELINES),
    );
    render(<SpecPipelinePanel />);
    fireEvent.click(await screen.findByText("spec-abc123"));
    expect(await screen.findByText("Pipeline detail unavailable — HTTP 500")).toBeTruthy();
  });

  it("every requested path is accepted by the proxy allowlist", async () => {
    const urls = stubFetch((url) =>
      url.includes("/api/spec-pipeline/spec-") ? jsonResponse(DETAIL) : jsonResponse(PIPELINES),
    );
    render(<SpecPipelinePanel />);
    fireEvent.click(await screen.findByText("spec-abc123"));
    await waitFor(() => expect(urls.some((u) => u.includes("/api/spec-pipeline/spec-abc123"))).toBe(true));
    for (const u of urls) {
      expect(u.startsWith(PREFIX)).toBe(true);
      expect(allowed(u.slice(PREFIX.length)), u).toBe(true);
    }
  });
});
