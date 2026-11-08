/**
 * Fleet version gate (08/11/2026) — the Fleet tile shows, per machine, which code it
 * runs against the approved version, its state, its last update and job, its local
 * edits and the blocker with the next action. Every value comes from the heartbeat's
 * `mesh-runner` entry in `agent_runtimes`; a missing value reads "unknown", never a guess.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { FleetView } from "@/lib/control/mesh-fleet";
import { displayState, projectFleet } from "@/lib/control/mesh-fleet";

const CHECKED = "2026-11-08T02:00:00.000Z";
const RUN = "a".repeat(40);
const MAIN = "b".repeat(40);

const RUNNER_ENTRY = {
  runtime: "mesh-runner", present: true, version: RUN, approved_version: MAIN,
  version_status: "outdated", state: "outdated", state_age_s: 30, current_task: null,
  hold_reason: "outdated: runtime has local edits; checkpoint them, then restore the runtime to HEAD",
  local_edits: 2, last_update: { outcome: "update refused: runtime has local edits", ts: 1794103200 },
  last_job: { linear_id: "RA-7487", state: "done", ts: 1794100000 },
  skills_version: null, heartbeat_version: RUN,
};

const UPSTREAM = {
  machines: [
    { host: "mini", version: "nexus-mesh/aaaaaaaaaaaa", status: "outdated", last_seen: "2026-11-08T01:59:40.000Z",
      is_stale: false, agent_runtimes: [{ runtime: "claude", present: true }, RUNNER_ENTRY] },
    { host: "macbook", version: "nexus-mesh/0.1", status: "online", last_seen: "2026-11-08T01:59:50.000Z",
      is_stale: false, agent_runtimes: [{ runtime: "claude", present: true }] },
  ],
  claims: [], errors: [],
};

let view: FleetView | null = null;
vi.mock("@/lib/boards/sources", () => ({ useSource: () => ({ seq: view ? 1 : 0, value: view }) }));

afterEach(() => {
  cleanup();
  view = null;
});

describe("projectFleet — mesh-runner entry", () => {
  it("maps the runner facts and the node status", () => {
    const projected = projectFleet(UPSTREAM, CHECKED);
    if (projected.status !== "ok") throw new Error("expected ok");
    const [mini, macbook] = projected.machines;
    expect(mini.status).toBe("outdated");
    expect(mini.runner).toMatchObject({
      version: RUN, approvedVersion: MAIN, versionStatus: "outdated", localEdits: 2,
      lastJob: { linearId: "RA-7487", state: "done", ts: 1794100000 },
    });
    expect(macbook.runner).toBeNull();          // no entry: unknown, not "current"
  });

  it("maps the shown states without inventing one", () => {
    const base = projectFleet(UPSTREAM, CHECKED);
    if (base.status !== "ok") throw new Error("expected ok");
    const m = base.machines[0];
    expect(displayState({ ...m, status: "working" })).toBe("busy");
    expect(displayState({ ...m, status: "online" })).toBe("idle");
    expect(displayState({ ...m, status: "quarantined" })).toBe("blocked (quarantined)");
    expect(displayState({ ...m, status: "hard_stop" })).toBe("hard_stop");
    expect(displayState({ ...m, stale: true })).toBe("offline");
    expect(displayState({ ...m, status: null })).toBe("unknown");
  });
});

describe("FleetTile — version rows", () => {
  it("renders unknown wherever the runner gave nothing", async () => {
    view = projectFleet(UPSTREAM, CHECKED);
    const { default: FleetTile } = await import("@/components/control/FleetTile");
    render(<FleetTile />);
    const row = within(screen.getByRole("article", { name: "macbook" }));
    for (const label of ["running", "approved", "match", "task", "last update", "last job", "local edits", "blocker", "next"]) {
      expect(row.getByText(`${label} unknown`)).toBeTruthy();
    }
    expect(row.getByText("state idle")).toBeTruthy();
    expect(row.getByText("heartbeat 10s ago")).toBeTruthy();
  });

  it("renders the runner facts, the blocker and the next action", async () => {
    view = projectFleet(UPSTREAM, CHECKED);
    const { default: FleetTile } = await import("@/components/control/FleetTile");
    render(<FleetTile />);
    const row = within(screen.getByRole("article", { name: "mini" }));
    expect(row.getByText("running aaaaaaaaaaaa")).toBeTruthy();
    expect(row.getByText("approved bbbbbbbbbbbb")).toBeTruthy();
    expect(row.getByText("match outdated")).toBeTruthy();
    expect(row.getByText("state outdated")).toBeTruthy();
    expect(row.getByText("local edits 2")).toBeTruthy();
    expect(row.getByText("blocker outdated: runtime has local edits")).toBeTruthy();
    expect(row.getByText("next checkpoint them, then restore the runtime to HEAD")).toBeTruthy();
    expect(row.getByText(/^last job RA-7487 done /)).toBeTruthy();
    expect(row.getByText(/^last update update refused: runtime has local edits /)).toBeTruthy();
  });
});
