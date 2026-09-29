/**
 * KillSwitchPanel — loaded, empty and error states (AAA check 7, MC-03).
 *
 * /api/kill-switch?op=status answers 200 even when upstream fails, with an
 * `error` field beside default false/0 values (app/api/kill-switch/route.ts
 * _quietStatus). The panel used to show those defaults as fact: "DISABLED",
 * lock "no", "0 / 0" approvers. A failed read is now UNKNOWN, and Halt stays
 * available because the operator must be able to stop the swarm regardless.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import KillSwitchPanel from "@/components/control/KillSwitchPanel";

function serve(body: unknown, status = 200) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status })));
}

const quiet = (error: string) => ({
  error, swarm_enabled_env: false, kill_switch_active: false, escalation_lock_active: false,
  panic_count_last_hour: 0, approver_allowlist: [], approver_totp_configured: [],
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("KillSwitchPanel", () => {
  it("LOADED: a halted swarm shows HALTED, the lock, panics and approvers, and offers Resume", async () => {
    serve({ swarm_enabled_env: true, kill_switch_active: true, escalation_lock_active: true,
      panic_count_last_hour: 3, approver_allowlist: ["a", "b"], approver_totp_configured: ["a"] });
    render(<KillSwitchPanel />);
    expect(await screen.findByText("HALTED")).toBeTruthy();
    expect(screen.getByText("LOCKED")).toBeTruthy();
    expect(screen.getByText("3")).toBeTruthy();
    expect(screen.getByText("1 / 2")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Resume swarm" })).toBeTruthy();
  });

  it("EMPTY: a disabled swarm with no panics or approvers reads as such and offers Halt", async () => {
    serve({ swarm_enabled_env: false, kill_switch_active: false, escalation_lock_active: false,
      panic_count_last_hour: 0, approver_allowlist: [], approver_totp_configured: [] });
    render(<KillSwitchPanel />);
    expect(await screen.findByText("DISABLED")).toBeTruthy();
    expect(screen.getByText("0 / 0")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Halt swarm" })).toBeTruthy();
  });

  it("ERROR: an upstream failure is UNKNOWN, not DISABLED with invented zeros", async () => {
    serve(quiet("upstream unreachable"));
    render(<KillSwitchPanel />);
    expect(await screen.findByText("upstream unreachable")).toBeTruthy();
    expect(screen.getByText("UNKNOWN")).toBeTruthy();
    expect(screen.getAllByText("unknown")).toHaveLength(3);
    expect(screen.queryByText("DISABLED")).toBeNull();
    expect(screen.queryByText("0 / 0")).toBeNull();
    expect(screen.getByRole("button", { name: "Halt swarm" })).toBeTruthy();
  });

  it("ERROR: a rejected fetch is UNKNOWN and shows the failure", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("network down"); }));
    render(<KillSwitchPanel />);
    expect(await screen.findByText("Error: network down")).toBeTruthy();
    expect(screen.getByText("UNKNOWN")).toBeTruthy();
    expect(screen.queryByText("DISABLED")).toBeNull();
  });
});
