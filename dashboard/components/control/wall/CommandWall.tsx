"use client";
// The /control wall: five live screens over the existing read-only feeds.
// No new endpoint, no write. Every screen states its own source state.
import { useSource, type KillSwitchStatus, type SourceState } from "@/lib/boards/sources";
import {
  CRM_REPO, SYNTHEX_REPO, WALL_REPOS, deriveAlerts, fleetFailureText, fleetTiles, prPipelineTone, prRow,
} from "@/lib/control/command-wall";
import type { FleetView } from "@/lib/control/mesh-fleet";
import type { MissionControlLive } from "@/lib/control/mission-control-live";
import { useRepoBoards } from "@/lib/control/useRepoBoards";
import type { WallSnapshot } from "@/lib/wall/snapshot";
import AlertTicker from "./AlertTicker";
import CampaignFlowScreen from "./CampaignFlowScreen";
import FleetScreen from "./FleetScreen";
import PrPipelineScreen from "./PrPipelineScreen";
import RevenueScreen from "./RevenueScreen";
import StatusBar from "./StatusBar";
import WallPanel, { STATE_TEXT, STATE_TONE } from "./WallPanel";
import styles from "./command-wall.module.css";

export default function CommandWall() {
  const wall = useSource<WallSnapshot | null>("wall");
  const fleet = useSource<FleetView>("mesh-fleet");
  const live = useSource<MissionControlLive>("mc-live");
  const kill = useSource<KillSwitchStatus>("kill-switch");
  const boards = useRepoBoards(WALL_REPOS);

  const tiles = fleetTiles(wall.value, fleet.value);
  const rows = WALL_REPOS.map((repo) => prRow(repo, boards[repo]?.board, boards[repo]?.reason));
  const sources: { id: string; label: string; state: SourceState; reason: string | null }[] = [
    { id: "wall", label: "Fleet heartbeats", state: wall.state, reason: wall.reason },
    { id: "mesh-fleet", label: "Fleet job claims", state: fleet.state, reason: fleet.reason },
    { id: "mc-live", label: "Mission Control backend", state: live.state, reason: live.reason },
    { id: "kill-switch", label: "Kill switch", state: kill.state, reason: kill.reason },
  ];
  const liveCount = sources.filter((s) => s.state === "live").length;
  const alerts = deriveAlerts({
    sources,
    observability: live.value?.observability,
    queue: live.value?.queue,
    killSwitch: kill.value,
    fleet: tiles,
    prs: rows,
  });
  const reposRead = rows.filter((r) => r.open !== null && r.ciReason === null).length;
  const allClear = liveCount === sources.length && reposRead === rows.length
    ? `No active alerts from ${sources.length} connected sources and ${rows.length} repositories`
    : `No alerts raised yet; ${sources.length - liveCount + rows.length - reposRead} of ${sources.length + rows.length} reads still connecting`;
  const pr = prPipelineTone(rows);
  const fleetFailure = fleetFailureText(wall.state, wall.reason);

  return (
    <div className={styles.wall} data-testid="command-wall">
      <StatusBar live={liveCount} total={sources.length} />
      <WallPanel id="wall-fleet" title="Fleet" area="fleet" stateText={STATE_TEXT[wall.state]} tone={STATE_TONE[wall.state]}>
        <FleetScreen tiles={tiles} failure={fleetFailure} />
      </WallPanel>
      <WallPanel id="wall-prs" title="PR pipeline" area="prs" stateText={pr.text} tone={pr.tone}>
        <PrPipelineScreen rows={rows} />
      </WallPanel>
      <WallPanel id="wall-flow" title="CRM to Synthex campaign flow" area="flow" stateText="not connected" tone="idle">
        <CampaignFlowScreen crm={rows.find((r) => r.repo === CRM_REPO)} synthex={rows.find((r) => r.repo === SYNTHEX_REPO)} />
      </WallPanel>
      <WallPanel id="wall-revenue" title="Revenue and funnel" area="rev" stateText="no data source yet" tone="idle">
        <RevenueScreen />
      </WallPanel>
      <AlertTicker alerts={alerts} allClearText={allClear} />
    </div>
  );
}
