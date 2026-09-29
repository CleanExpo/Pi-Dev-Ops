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
  // WP-09 check 5: this page's own data is rendered on the server, so cutting
  // browser calls only cuts the shell's. Only these pages may score N/A there;
  // any other page that goes silent fails. Set from the 29 Sept local run.
  serverRendered?: true;
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
  // #828 replaced the "Command deck" hero with PortfolioFocus; its h2 renders in
  // loading, error and loaded states alike (components/control/PortfolioFocus.tsx).
  { id: "MC-01", path: "/control", landmark: heading("Choose a project. See the work.") },
  ...CONTROL_SECTIONS.map((item) => ({
    id: CONTROL_IDS[item.slug],
    path: item.href,
    landmark: heading(item.title),
    // MC-07 (build) fetches nothing of its own; its calls are the TopBar's.
    ...(item.slug === "build" ? { serverRendered: true as const } : {}),
  })),
  { id: "MC-13", path: "/command-centre", landmark: heading("Command Centre"), serverRendered: true },
  { id: "MC-14", path: "/command-centre/hermes", landmark: heading("Hermes Control Panel"), serverRendered: true },
  { id: "MC-15", path: "/command-centre/knowledge", landmark: heading("Wiki Knowledge Base") },
  { id: "MC-16", path: "/command-centre/providers", landmark: heading("Providers") },
  { id: "MC-17", path: "/command-centre/wall", landmark: { kind: "testid", id: "wall-banner" } },
  // MC-18 reads wiki_pages on the server; WikiGraphCanvas only draws its props.
  // Its check-5 pass came from the missing-key error, gone once the key landed.
  { id: "MC-18", path: "/command-centre/wiki-graph", landmark: heading("Wiki Graph"), serverRendered: true },
  {
    id: "MC-19",
    path: "/command-centre/youtube-intent",
    landmark: heading("UG-N Intent-Only YouTube Catalog"),
    serverRendered: true,
  },
];
