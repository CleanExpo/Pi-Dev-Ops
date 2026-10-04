/**
 * RA-7898 A2, A5, A9 and T7 — request counts, the signed-out kill switch, a
 * write inside a board, and the request-sharing tap.
 */
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import FleetTile from "@/components/control/FleetTile";
import KillSwitchPanel from "@/components/control/KillSwitchPanel";
import { ModuleFrame } from "@/components/boards/ModuleFrame";
import { ProviderUsageCockpit } from "@/components/command-centre/provider-usage/ProviderUsageCockpit";
import { installFetchTap, TAP_TIMEOUT_MS, useFetchTap } from "@/lib/boards/sources/fetch-tap";
import { useSource } from "@/lib/boards/sources";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pathOf = (input: unknown) => new URL(String(input), "http://x").pathname;

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("A2 — one request per interval, however many readers", () => {
  it("two Fleet tiles make one /api/mesh-fleet request per 20 s", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn(async () => json({ status: "ok", checkedAt: new Date().toISOString(), machines: [] }));
    vi.stubGlobal("fetch", fetchMock);
    render(<><FleetTile /><FleetTile /></>);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("two Fleet modules on a board make one request per 20 s", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn(async (_url: string) => json({ status: "ok", checkedAt: new Date().toISOString(), machines: [] }));
    vi.stubGlobal("fetch", fetchMock);
    render(<>
      <ModuleFrame item={{ id: "a", module: "fleet", view: "tile" }} />
      <ModuleFrame item={{ id: "b", module: "fleet", view: "tile" }} />
    </>);
    await act(async () => { await vi.advanceTimersByTimeAsync(40_001); });
    expect(fetchMock.mock.calls.filter(([u]) => pathOf(u) === "/api/mesh-fleet")).toHaveLength(3);
  });
});

describe("A5 — kill switch answering 401", () => {
  it.each([
    ["on its own page", () => <KillSwitchPanel />],
    ["on a board", () => <ModuleFrame item={{ id: "k", module: "kill-switch", view: "panel" }} />],
  ])("%s: Halt is disabled and the reason is shown", async (_where, Ui) => {
    vi.stubGlobal("fetch", vi.fn(async () => json({ error: "Unauthorised" }, 401)));
    render(<Ui />);
    const halt = await screen.findByRole("button", { name: "Halt swarm" });
    await vi.waitFor(() => expect(halt).toBeDisabled());
    expect(screen.getAllByText("Signed out — sign in again (401)").length).toBeGreaterThan(0);
  });
});

describe("A9 — a write inside a board", () => {
  it("Halt opens the existing modal; a 200 closes it and one immediate re-read shows HALTED", async () => {
    let halted = false;
    const calls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push(`${method} ${input}`);
      if (method === "POST") { halted = true; return json({ ok: true }); }
      return json({ swarm_enabled_env: true, kill_switch_active: halted, escalation_lock_active: false,
        panic_count_last_hour: 0, approver_allowlist: ["ana", "ben"], approver_totp_configured: ["ana", "ben"] });
    }));
    render(<ModuleFrame item={{ id: "k", module: "kill-switch", view: "panel" }} />);
    fireEvent.click(await screen.findByRole("button", { name: "Halt swarm" }));
    const dialog = await screen.findByRole("dialog");
    const selects = within(dialog).getAllByRole("combobox");
    fireEvent.change(selects[0], { target: { value: "ana" } });
    fireEvent.change(selects[1], { target: { value: "ben" } });
    const codes = within(dialog).getAllByPlaceholderText("123456");
    fireEvent.change(codes[0], { target: { value: "123456" } });
    fireEvent.change(codes[1], { target: { value: "654321" } });
    const getsBefore = calls.filter((c) => c.startsWith("GET")).length;
    fireEvent.click(within(dialog).getByRole("button", { name: "Halt swarm" }));
    expect(await screen.findByText("HALTED")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(calls.filter((c) => c.startsWith("POST"))).toEqual(["POST /api/kill-switch?op=kill"]);
    expect(calls.filter((c) => c.startsWith("GET")).length - getsBefore).toBe(1);
  });
});

function Shared() {
  useSource("provider-usage");
  return null;
}

describe("T7 — request-sharing tap", () => {
  const payload = () => ({ source: "cc:provider-usage", generatedAt: new Date().toISOString(),
    summary: { total: 0, available: 0, watching: 0, nearLimit: 0, blocked: 0, unknown: 0 }, providers: [], routing: [] });

  it("two cockpits plus the shared source make one network GET per 30 s", async () => {
    vi.useFakeTimers();
    const network = vi.fn(async (input: string) => (pathOf(input) === "/api/command-centre/provider-usage" ? json(payload()) : json({})));
    vi.stubGlobal("fetch", network);
    const uninstall = installFetchTap();
    render(<><ProviderUsageCockpit /><ProviderUsageCockpit /><Shared /></>);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    const usage = () => network.mock.calls.filter(([u]) => pathOf(u) === "/api/command-centre/provider-usage").length;
    expect(usage()).toBe(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(usage()).toBe(3);
    uninstall();
  });

  it("installed by a page, the tap is in place before its modules' first reads", async () => {
    vi.useFakeTimers();
    const network = vi.fn(async (input: string) => (pathOf(input) === "/api/command-centre/provider-usage" ? json(payload()) : json({})));
    vi.stubGlobal("fetch", network);
    function Page() {
      useFetchTap();
      return <><ProviderUsageCockpit /><ProviderUsageCockpit /><Shared /></>;
    }
    render(<Page />);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(network.mock.calls.filter(([u]) => pathOf(u) === "/api/command-centre/provider-usage")).toHaveLength(1);
  });

  it("a hung shared request is dropped when its last caller aborts, so the next read reaches the network", async () => {
    const network = vi.fn((_u: string, _i?: RequestInit) => new Promise<Response>(() => {}));
    vi.stubGlobal("fetch", network);
    const uninstall = installFetchTap();
    const caller = new AbortController();
    const first = window.fetch("/api/command-centre/provider-usage", { signal: caller.signal });
    caller.abort();
    await expect(first).rejects.toBeDefined();
    void window.fetch("/api/command-centre/provider-usage").catch(() => undefined);
    expect(network).toHaveBeenCalledTimes(2);
    expect(network.mock.calls[0][1]?.signal?.aborted).toBe(true);
    uninstall();
  });

  it("a hung shared request times out and frees the path", async () => {
    vi.useFakeTimers();
    const network = vi.fn((_u: string, _i?: RequestInit) => new Promise<Response>(() => {}));
    vi.stubGlobal("fetch", network);
    const uninstall = installFetchTap();
    const first = window.fetch("/api/command-centre/provider-usage");
    const settled = expect(first).rejects.toBeDefined();
    await vi.advanceTimersByTimeAsync(TAP_TIMEOUT_MS);
    await settled;
    void window.fetch("/api/command-centre/provider-usage").catch(() => undefined);
    expect(network).toHaveBeenCalledTimes(2);
    uninstall();
  });

  it("any other request reaches the original fetch unchanged, and uninstall restores it", async () => {
    const network = vi.fn(async (_u: string, _i?: RequestInit) => json({}));
    vi.stubGlobal("fetch", network);
    const original = window.fetch;
    const uninstall = installFetchTap();
    expect(window.fetch).not.toBe(original);
    const init = { method: "POST", body: "x" };
    await window.fetch("/api/kill-switch?op=kill", init);
    await window.fetch("/api/command-centre/provider-usage", { method: "POST" });
    expect(network.mock.calls[0]).toEqual(["/api/kill-switch?op=kill", init]);
    expect(network.mock.calls[1]).toEqual(["/api/command-centre/provider-usage", { method: "POST" }]);
    uninstall();
    expect(window.fetch).toBe(original);
  });
});
