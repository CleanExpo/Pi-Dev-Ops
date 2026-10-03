// RA-7898 — Knowledge sector.
import { CuratorView, WikiGraphView } from "@/components/boards/views/panels";
import type { ModuleDef } from "./types";

export const KNOWLEDGE_MODULES: ModuleDef[] = [
  {
    id: "curator", name: "Curator proposals", sector: "Knowledge", sources: ["curator"], minSize: { w: 3, h: 4 }, action: false,
    blurb: "Pending skill proposals from the curator. Read-only.",
    views: { list: { label: "Pending list", size: { w: 6, h: 7 }, component: CuratorView } },
  },
  {
    id: "wiki-graph", name: "Wiki graph", sector: "Knowledge", sources: ["wiki-graph"], minSize: { w: 3, h: 3 }, action: false,
    blurb: "Pages and links in the wiki knowledge graph.",
    views: { tile: { label: "Summary tile", size: { w: 4, h: 4 }, component: WikiGraphView } },
  },
];
