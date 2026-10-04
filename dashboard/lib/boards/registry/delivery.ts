// RA-7898 — Delivery sector.
import { ActivityPulse, ActivityTimeline, BuildsNumber, BuildsTable } from "@/components/boards/views/activity-builds";
import { BuildsBoard } from "@/components/boards/views/builds";
import { ChainRing, ChainRow } from "@/components/boards/views/fleet-chain";
import { IdeaFunnel, IdeaInbox } from "@/components/boards/views/ideas-safety";
import { IdeaPipelineView, LiveActivityView } from "@/components/boards/views/panels";
import { WallStationsView } from "@/components/boards/views/wall";
import type { ModuleDef } from "./types";

export const DELIVERY_MODULES: ModuleDef[] = [
  {
    id: "ship-chain", name: "Ship chain", sector: "Delivery", sources: ["wall"], minSize: { w: 3, h: 3 }, action: false,
    blurb: "Seven stations from idea to learning. Grey means no live source yet.",
    views: {
      accordion: { label: "Accordion", size: { w: 4, h: 8 }, component: WallStationsView },
      row: { label: "Station row", size: { w: 8, h: 3 }, component: ChainRow },
      ring: { label: "Ring", size: { w: 4, h: 4 }, component: ChainRing },
    },
  },
  {
    id: "activity", name: "Live activity", sector: "Delivery", sources: ["mc-live"], minSize: { w: 3, h: 4 }, action: false,
    blurb: "What the estate is doing right now: running sessions, completions, queue.",
    views: {
      feed: { label: "Feed", size: { w: 6, h: 8 }, component: LiveActivityView },
      timeline: { label: "Timeline", size: { w: 4, h: 6 }, component: ActivityTimeline },
      pulse: { label: "Pulse", size: { w: 3, h: 4 }, component: ActivityPulse },
    },
  },
  {
    id: "ideas", name: "Ideas", sector: "Delivery", sources: ["idea-pipeline"], minSize: { w: 4, h: 5 }, action: true,
    blurb: "Drop an idea, read its Board packet, say GO. Writes go through the existing idea routes.",
    views: {
      packet: { label: "Board packet", size: { w: 6, h: 9 }, component: IdeaPipelineView, action: true },
      funnel: { label: "Funnel", size: { w: 4, h: 5 }, component: IdeaFunnel },
      inbox: { label: "Inbox", size: { w: 4, h: 5 }, component: IdeaInbox },
    },
  },
  {
    id: "builds", name: "Builds", sector: "Delivery", sources: ["sessions"], minSize: { w: 3, h: 3 }, action: false,
    blurb: "Every build session by stage.",
    views: {
      board: { label: "Board by stage", size: { w: 8, h: 5 }, component: BuildsBoard },
      table: { label: "Table", size: { w: 6, h: 5 }, component: BuildsTable },
      number: { label: "Big number", size: { w: 3, h: 3 }, component: BuildsNumber },
    },
  },
];
