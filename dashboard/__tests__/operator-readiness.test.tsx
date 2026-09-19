import React from "react";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import OverviewPage from "@/app/(main)/overview/page";
import BrainStatusPanel from "@/components/brain/BrainStatusPanel";
import CeoHealthPanel from "@/components/CeoHealthPanel";

const response = (body: unknown, ok = true) => ({ ok, headers: new Headers(), json: async () => body }) as Response;

function overviewFetch(health: unknown, sessions: unknown = []) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => response(url.endsWith("/health") ? health : sessions)));
}

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("operator readiness", () => {
  it("shows blocked generation separately from an armed automation loop", async () => {
    overviewFetch({ status: "ok", autonomy: { enabled: true, armed: true }, generation: {
      transport: "anthropic_agent_sdk", status: "blocked", ready: false,
      blockers: ["Subscription authorization unavailable"], auth_verified: false, cost_verified: false,
    } });
    render(<OverviewPage />);
    expect(await screen.findByText("Generation blocked")).toBeInTheDocument();
    expect(screen.getByText("Subscription authorization unavailable")).toBeInTheDocument();
    expect(screen.getAllByText("Armed", { exact: true }).length).toBeGreaterThan(0);
  });
  it("preserves Main navigation while rejecting a proxy fallback as live evidence", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, headers: new Headers({ "X-Upstream-Status": "502" }),
      json: async () => ({ status: "ok" }),
    })));
    render(<OverviewPage />);
    expect(await screen.findByText("Service status unavailable")).toBeInTheDocument();
    expect(screen.getByText("Session status unavailable")).toBeInTheDocument();
    expect(screen.queryByText("Service reachable")).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Run a build/ })[0]).toHaveAttribute("href", "/control/build");
    expect(screen.getAllByRole("link", { name: /Goal/ })[0]).toHaveAttribute("href", "/control/goal");
  });
  it("does not upgrade an unverified generator to ready", async () => {
    overviewFetch({ status: "ok", generation: { status: "unverified", ready: null, blockers: [] } });
    render(<OverviewPage />);
    expect(await screen.findByText("unverified", { exact: true })).toBeInTheDocument();
    expect(screen.getByText("Readiness unknown")).toBeInTheDocument();
  });
  it("does not equate a liveness probe with operational readiness or billing evidence", async () => {
    overviewFetch({ status: "ok" });
    render(<OverviewPage />);
    expect(await screen.findByText("Service reachable")).toBeInTheDocument();
    expect(screen.getByText("Readiness unknown")).toBeInTheDocument();
    expect(screen.getByText("Billing not observed")).toBeInTheDocument();
    expect(screen.getByText("Delivery not verified")).toBeInTheDocument();
    expect(screen.queryByText("Active", { exact: true })).not.toBeInTheDocument();
  });

  it("places stalled work and a recovery navigation action ahead of activity", async () => {
    overviewFetch({ status: "ok", autonomy: { enabled: true, armed: true } }, [
      { id: "stalled-123", repo: "https://github.com/org/project", status: "stalled", started: 1789780000, last_phase: "evaluate" },
    ]);
    render(<OverviewPage />);
    const attention = await screen.findByRole("region", { name: "Needs attention" });
    expect(within(attention).getByText("org/project")).toBeInTheDocument();
    expect(within(attention).getByText("stalled", { exact: true })).toBeInTheDocument();
    expect(within(attention).getByRole("link", { name: /inspect build/i })).toHaveAttribute("href", "/builds");
    expect(screen.getByText("Work blocked")).toBeInTheDocument();
  });

  it("labels intentionally disarmed automation as paused", async () => {
    overviewFetch({ status: "ok", autonomy: { enabled: true, armed: false } });
    render(<OverviewPage />);
    expect(await screen.findByText("Automation paused")).toBeInTheDocument();
  });

  it("does not turn a session complete label into verified delivery", async () => {
    overviewFetch({ status: "ok" }, [{ id: "done-123", repo: "org/project", status: "complete", started: "2026-09-19T00:00:00Z" }]);
    render(<OverviewPage />);
    expect(await screen.findByText("Reported complete")).toBeInTheDocument();
    expect(screen.getByText("Delivery not verified")).toBeInTheDocument();
  });

  it("shows documentation freshness separately from model availability", async () => {
    overviewFetch({ status: "ok", model_documentation: { status: "stale", model_registry_verified: false } });
    render(<OverviewPage />);
    expect(await screen.findByText("stale", { exact: true })).toBeInTheDocument();
    expect(screen.getByText(/Documentation freshness does not verify model availability/)).toBeInTheDocument();
    expect(screen.getByText("Readiness unknown")).toBeInTheDocument();
  });

  it("keeps health visible when the independent sessions request fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.endsWith("/health")) return response({ status: "ok" });
      throw new Error("offline");
    }));
    render(<OverviewPage />);
    expect(await screen.findByText("Service reachable")).toBeInTheDocument();
    expect(screen.getByText("Session status unavailable")).toBeInTheDocument();
    expect(screen.queryByText("No sessions yet.")).not.toBeInTheDocument();
  });

  it("rejects malformed health and session items without crashing", async () => {
    overviewFetch({ status: { bad: true }, autonomy: "armed" }, [null, {}, { id: "bad" }]);
    render(<OverviewPage />);
    expect(await screen.findByText("Service status unavailable")).toBeInTheDocument();
    expect(screen.getByText("Session status unavailable")).toBeInTheDocument();
  });

  it("withdraws previous success after an unsuccessful refresh", async () => {
    vi.useFakeTimers();
    let healthy = true;
    vi.stubGlobal("fetch", vi.fn(async (url: string) => response(url.endsWith("/health") ? { status: "ok" } : [], healthy)));
    render(<OverviewPage />);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(screen.getByText("Service reachable")).toBeInTheDocument();
    healthy = false;
    await act(async () => { await vi.advanceTimersByTimeAsync(15_000); });
    expect(screen.getByText("Service status unavailable")).toBeInTheDocument();
    expect(screen.getByText("Session status unavailable")).toBeInTheDocument();
    expect(screen.queryByText("Service reachable")).not.toBeInTheDocument();
  });

  it("does not treat a malformed Brain probe as connected", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => response({ ok: "yes" })));
    render(<BrainStatusPanel />);
    expect(await screen.findByText("Probe unreachable")).toBeInTheDocument();
  });

  it("times out an unresponsive health refresh instead of retaining success", async () => {
    vi.useFakeTimers();
    let hangs = false;
    vi.stubGlobal("fetch", vi.fn(async (url: string, options: RequestInit) => {
      if (!url.endsWith("/health")) return response([]);
      if (!hangs) return response({ status: "ok" });
      return new Promise<Response>((_, reject) => options.signal?.addEventListener("abort", () => reject(new Error("timeout"))));
    }));
    render(<OverviewPage />);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(screen.getByText("Service reachable")).toBeInTheDocument();
    hangs = true;
    await act(async () => { await vi.advanceTimersByTimeAsync(25_000); });
    expect(screen.getByText("Service status unavailable")).toBeInTheDocument();
    expect(screen.queryByText("Service reachable")).not.toBeInTheDocument();
  });

  it("removes stale success when refreshing the Brain probe fails", async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(response({ ok: true, checked_at: "2026-09-19T00:00:00Z" }))
      .mockResolvedValueOnce(response({ ok: true }, false));
    vi.stubGlobal("fetch", fetcher);
    render(<BrainStatusPanel />);
    expect(await screen.findByText("Connected")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Re-check" }));
    expect(await screen.findByText("Probe unreachable")).toBeInTheDocument();
    expect(screen.queryByText("Connected", { exact: true })).not.toBeInTheDocument();
    expect(screen.getByText(/Historical snapshot/)).toHaveTextContent("2026-06-11");
    expect(screen.queryByText("Done", { exact: true })).not.toBeInTheDocument();
  });

  it("sidebar describes reachability without inventing active swarm state", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => response({ status: "ok" })));
    render(<CeoHealthPanel />);
    await waitFor(() => expect(screen.getByText("REACHABLE")).toBeInTheDocument());
    expect(screen.getByText("Unknown")).toBeInTheDocument();
    expect(screen.queryByText("Active")).not.toBeInTheDocument();
    expect(screen.queryByText("OK", { exact: true })).not.toBeInTheDocument();
  });

  it("withdraws sidebar reachability when a later health request hangs", async () => {
    vi.useFakeTimers();
    let hangs = false;
    vi.stubGlobal("fetch", vi.fn(async (_url: string, options?: RequestInit) => {
      if (!hangs) return response({ status: "ok" });
      return new Promise<Response>((_, reject) => options?.signal?.addEventListener("abort", () => reject(new Error("timeout"))));
    }));
    render(<CeoHealthPanel />);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(screen.getByText("REACHABLE")).toBeInTheDocument();
    hangs = true;
    await act(async () => { await vi.advanceTimersByTimeAsync(40_000); });
    expect(screen.getByText("Backend unreachable")).toBeInTheDocument();
    expect(screen.queryByText("REACHABLE")).not.toBeInTheDocument();
  });

  it("ends an unresponsive Brain probe and enables another check", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn(async (_url: string, options?: RequestInit) =>
      new Promise<Response>((_, reject) => options?.signal?.addEventListener("abort", () => reject(new Error("timeout"))))));
    render(<BrainStatusPanel />);
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
    expect(screen.getByText("Probe unreachable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Re-check" })).toBeEnabled();
  });
});
