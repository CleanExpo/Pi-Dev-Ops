// RA-7898 — Machines sector.
import { FleetList, FleetStrip } from "@/components/boards/views/fleet-chain";
import { LaneList } from "@/components/boards/views/lanes";
import { FleetTileView } from "@/components/boards/views/panels";
import { WallFleetView } from "@/components/boards/views/wall";
import type { ModuleDef } from "./types";

export const MACHINE_MODULES: ModuleDef[] = [
  {
    id: "fleet", name: "Fleet", sector: "Machines", sources: ["mesh-fleet"], minSize: { w: 3, h: 3 }, action: false,
    blurb: "Each machine's revision, last heartbeat and current claim.",
    views: {
      tile: { label: "Machine list", size: { w: 4, h: 5 }, component: FleetTileView },
      strip: { label: "Heartbeat strip", size: { w: 6, h: 3 }, component: FleetStrip },
      list: { label: "Compact list", size: { w: 4, h: 3 }, component: FleetList },
    },
  },
  {
    id: "wall-fleet", name: "Fleet board", sector: "Machines", sources: ["wall"], minSize: { w: 4, h: 4 }, action: false,
    blurb: "The wall's fleet tiles: each machine and its agents, self-reported.",
    views: { tiles: { label: "Wall tiles", size: { w: 8, h: 6 }, component: WallFleetView } },
  },
  {
    id: "claude-lanes", name: "Claude lanes", sector: "Machines", sources: ["mesh-lanes"], minSize: { w: 4, h: 3 }, action: false,
    blurb: "Each Claude Code session reporting through the mc-lane mod: last tool, context, limit and cost.",
    views: { list: { label: "Lane list", size: { w: 6, h: 4 }, component: LaneList } },
  },
];
