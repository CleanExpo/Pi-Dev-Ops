// RA-7898 — Safety sector.
import { KillDetail, KillLight } from "@/components/boards/views/ideas-safety";
import { KillSwitchView, SwarmView } from "@/components/boards/views/panels";
import type { ModuleDef } from "./types";

export const SAFETY_MODULES: ModuleDef[] = [
  {
    id: "swarm", name: "Swarm", sector: "Safety", sources: ["swarm-status", "kill-switch"], minSize: { w: 3, h: 5 }, action: true,
    blurb: "Swarm state, autonomous PR progress, and the kill switch.",
    views: { panel: { label: "Swarm panel", size: { w: 4, h: 9 }, component: SwarmView, action: true } },
  },
  {
    id: "kill-switch", name: "Kill switch", sector: "Safety", sources: ["kill-switch"], minSize: { w: 3, h: 4 }, action: true,
    blurb: "Halt and resume the swarm. Works only behind your sign-in.",
    views: {
      panel: { label: "Controls", size: { w: 3, h: 5 }, component: KillSwitchView, action: true },
      light: { label: "Status light", size: { w: 4, h: 4 }, component: KillLight },
      detail: { label: "Detail", size: { w: 4, h: 5 }, component: KillDetail },
    },
  },
];
