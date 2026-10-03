/**
 * RA-7898 T8 — view #1 fidelity: each existing panel, rendered inside a board
 * card in the live state, produces exactly the markup it produces on its own
 * page, given the same responses (docs/specs/modular-boards.md §4.1).
 */
import { act, cleanup, render } from "@testing-library/react";
import type { ComponentType } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ModuleFrame from "@/components/boards/ModuleFrame";
import CuratorProposalsPanel from "@/components/control/CuratorProposalsPanel";
import FleetTile from "@/components/control/FleetTile";
import HealthGrid from "@/components/control/HealthGrid";
import IdeaPipelinePanel from "@/components/control/IdeaPipelinePanel";
import KillSwitchPanel from "@/components/control/KillSwitchPanel";
import LiveActivityFeed from "@/components/control/LiveActivityFeed";
import ModelFabricPanel from "@/components/control/ModelFabricPanel";
import PortfolioFocus from "@/components/control/PortfolioFocus";
import SwarmPanel from "@/components/control/SwarmPanel";
import { resetSources } from "@/lib/boards/sources/poller";

const NOW = new Date("2026-10-03T00:00:00Z");
const iso = (agoS = 0) => new Date(NOW.getTime() - agoS * 1000).toISOString();

const RESPONSES: Record<string, unknown> = {
  "/api/mesh-fleet": { status: "ok", checkedAt: iso(), machines: [{ host: "desk", revision: "abc", lastHeartbeat: iso(8), currentClaim: "RA-1", stale: false }] },
  "/api/model-fabric": { enabled: true, healthy: true, totals: { calls: 10, failures: 1 }, lanes: { review: { model: "m3", banned: false } } },
  "/api/swarm-status": { state: "SHADOW", autonomous_prs_today: 1, autonomous_prs_limit: 3, green_merges: 4, green_merges_target: 20, last_pr_ts: null, last_pr_url: null },
  "/api/kill-switch": { swarm_enabled_env: true, kill_switch_active: false, escalation_lock_active: false, panic_count_last_hour: 0, approver_allowlist: ["a", "b"], approver_totp_configured: ["a"] },
  "/api/curator-proposals": { total: 1, returned: 1, by_status: { pending: 1 }, proposals: [{ proposal_id: "p", ts: iso(60), status: "pending", proposed_skill_name: "notes" }] },
  "/api/pi-ceo/api/projects/health": [{ project_id: "RA", repo: "CleanExpo/RA", overall_health: 86, scores: { security: 86 }, findings_count: {}, deployments: {} }],
  "/api/pi-ceo/api/mission-control/live": { ts: iso(), active_sessions: [], recent_completions: [], throughput: { hourly: [1, 2] } },
  "/api/pi-ceo/api/pipelines": [],
  "/api/pi-ceo/api/idea-pipeline": { snapshot: { intake: "", north_star: "", awaiting: 0, packet: null, verdicts: [], go_required: true, executed: false } },
};

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: false });
  vi.setSystemTime(NOW);
  vi.stubGlobal("fetch", vi.fn(async (input: string) => {
    const path = new URL(String(input), "http://x").pathname;
    return new Response(JSON.stringify(RESPONSES[path] ?? {}), { status: 200 });
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });

async function settle() {
  await act(async () => { await vi.advanceTimersByTimeAsync(5); });
}

const PANELS: [string, string, ComponentType][] = [
  ["fleet", "tile", FleetTile],
  ["activity", "feed", LiveActivityFeed],
  ["ideas", "packet", IdeaPipelinePanel],
  ["portfolio", "focus", PortfolioFocus],
  ["swarm", "panel", SwarmPanel],
  ["kill-switch", "panel", KillSwitchPanel],
  ["models", "panel", ModelFabricPanel],
  ["health", "grid", HealthGrid],
  ["curator", "list", CuratorProposalsPanel],
];

describe("view #1 renders the same markup inside a board card", () => {
  it.each(PANELS)("%s", async (module, view, Panel) => {
    const alone = render(<Panel />);
    await settle();
    const expected = alone.container.innerHTML;
    expect(expected.length).toBeGreaterThan(50);
    alone.unmount();
    resetSources();

    const framed = render(<ModuleFrame item={{ id: "x", module, view }} />);
    await settle();
    const article = framed.container.querySelector("article")!;
    expect(article.getAttribute("data-state")).toBe("live");
    const body = article.querySelector(":scope > div:not([data-testid])")!;
    expect(body.innerHTML).toBe(expected);
  });
});
