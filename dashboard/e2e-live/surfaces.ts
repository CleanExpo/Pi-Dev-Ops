import { CONTROL_SECTIONS } from "../lib/control/nav";

// WP-06 (docs/plans/mission-control/work-packages.md): the 20 register rows in
// docs/plans/mission-control/coverage-register.md, each with the element that
// proves the page rendered itself rather than the login page or app/error.tsx.
// This is a landmark, NOT a real-data assertion: a page showing its own empty
// state still passes check 1. Per-surface data assertions are sized from the
// first live run's receipts, as the plan says.
export interface LiveSurface {
  id: string;
  path: string;
  landmark: { kind: "heading"; text: string } | { kind: "testid"; id: string };
}

const CONTROL_IDS: Record<string, string> = {
  goal: "MC-02",
  swarm: "MC-03",
  model: "MC-04",
  health: "MC-05",
  roles: "MC-06",
  build: "MC-07",
  runs: "MC-08",
  curator: "MC-09",
  margot: "MC-10",
  pipeline: "MC-11",
  terminal: "MC-12",
};

const heading = (text: string): LiveSurface["landmark"] => ({ kind: "heading", text });

export const LIVE_SURFACES: readonly LiveSurface[] = [
  // MC-00 (the shell) is proved by control-hub.spec.ts: all nav labels visible.
  { id: "MC-01", path: "/control", landmark: heading("Command deck") },
  ...CONTROL_SECTIONS.map((item) => ({
    id: CONTROL_IDS[item.slug],
    path: item.href,
    landmark: heading(item.title),
  })),
  { id: "MC-13", path: "/command-centre", landmark: heading("Command Centre") },
  { id: "MC-14", path: "/command-centre/hermes", landmark: heading("Hermes Control Panel") },
  { id: "MC-15", path: "/command-centre/knowledge", landmark: heading("Wiki Knowledge Base") },
  { id: "MC-16", path: "/command-centre/providers", landmark: heading("Providers") },
  { id: "MC-17", path: "/command-centre/wall", landmark: { kind: "testid", id: "wall-banner" } },
  { id: "MC-18", path: "/command-centre/wiki-graph", landmark: heading("Wiki Graph") },
  {
    id: "MC-19",
    path: "/command-centre/youtube-intent",
    landmark: heading("UG-N Intent-Only YouTube Catalog"),
  },
];
