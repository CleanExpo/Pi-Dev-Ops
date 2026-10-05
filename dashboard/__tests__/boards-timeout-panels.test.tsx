/**
 * RA-7898 — a status read that never answers is a failed read once the shared
 * poller gives up at 10 s. Each panel must then show the failure, never stay
 * on its first-load "checking" / "loading" state.
 */
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CuratorProposalsPanel from "@/components/control/CuratorProposalsPanel";
import FleetTile from "@/components/control/FleetTile";
import KillSwitchPanel from "@/components/control/KillSwitchPanel";
import ModelFabricPanel from "@/components/control/ModelFabricPanel";
import SwarmPanel from "@/components/control/SwarmPanel";
import { resetSources } from "@/lib/boards/sources";

afterEach(() => { cleanup(); resetSources(); vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("a hung status read, after the 10 s timeout", () => {
  it.each([
    ["KillSwitchPanel", () => <KillSwitchPanel />],
    ["CuratorProposalsPanel", () => <CuratorProposalsPanel />],
    ["FleetTile", () => <FleetTile />],
    ["ModelFabricPanel", () => <ModelFabricPanel />],
    ["SwarmPanel", () => <SwarmPanel />],
  ])("%s shows the timeout, not a loading state", async (_name, Ui) => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => {})));
    render(<Ui />);
    await act(async () => { await vi.advanceTimersByTimeAsync(10_001); });
    expect(screen.getAllByText(/no answer within 10 s/).length).toBeGreaterThan(0);
  });

  it.each([
    ["KillSwitchPanel", () => <KillSwitchPanel />],
    ["CuratorProposalsPanel", () => <CuratorProposalsPanel />],
    ["ModelFabricPanel", () => <ModelFabricPanel />],
  ])("%s: a 200 whose error is not text shows a failure, never crashes", async (_name, Ui) => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: {} }), { status: 200 })));
    render(<Ui />);
    expect((await screen.findAllByText(/invalid error field/)).length).toBeGreaterThan(0);
  });

  it("KillSwitchPanel: a partial 200 is UNKNOWN, never '0 / 0' approvers", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ kill_switch_active: false, swarm_enabled_env: true }), { status: 200 })));
    render(<KillSwitchPanel />);
    expect(await screen.findByText("UNKNOWN")).toBeTruthy();
    expect(screen.queryByText("0 / 0")).toBeNull();
  });

  it("FleetTile: a 503 with an ok-shaped empty fleet is not 'No machines enrolled'", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(
      JSON.stringify({ status: "ok", checkedAt: "2026-10-04T00:00:00Z", machines: [] }), { status: 503 })));
    render(<FleetTile />);
    expect(await screen.findByText(/fleet read failed/)).toBeTruthy();
    expect(screen.queryByText(/No machines enrolled/)).toBeNull();
  });

  it("KillSwitchPanel reads UNKNOWN, not CHECKING, and keeps Halt", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => {})));
    render(<KillSwitchPanel />);
    await act(async () => { await vi.advanceTimersByTimeAsync(10_001); });
    expect(screen.getByText("UNKNOWN")).toBeTruthy();
    expect(screen.queryByText("CHECKING")).toBeNull();
    expect(screen.getByRole("button", { name: "Halt swarm" })).toBeTruthy();
  });
});
