export const CONTROL_SECTION_SLUGS = [
  "goal",
  "swarm",
  "model",
  "health",
  "roles",
  "build",
  "runs",
  "curator",
  "margot",
  "pipeline",
  "terminal",
] as const;

export const SPECIALIST_CONTROL_SLUGS = [
  "curator",
  "margot",
  "pipeline",
  "terminal",
] as const;

export const SPECIALIST_TILE_NOTE = "Specialist. Not the Goal path.";

export type ControlSectionSlug = (typeof CONTROL_SECTION_SLUGS)[number];

export interface ControlNavItem {
  href: string;
  slug: string;
  label: string;
  title: string;
  blurb: string;
}

export const CONTROL_HUB: ControlNavItem = {
  href: "/control",
  slug: "",
  label: "Live",
  title: "Mission Control",
  blurb: "Watch sessions after a ticket is Ready for Pi-Dev with pi-dev:autonomous.",
};

export const CONTROL_SECTIONS: readonly ControlNavItem[] = [
  {
    href: "/control/goal",
    slug: "goal",
    label: "Goal",
    title: "Goal → Linear",
    blurb: "Create a project brief. State the goal. Review drafts. Write to Linear.",
  },
  {
    href: "/control/swarm",
    slug: "swarm",
    label: "Swarm",
    title: "Swarm",
    blurb: "Autonomous PR progress and kill switch.",
  },
  {
    href: "/control/model",
    slug: "model",
    label: "Models",
    title: "Model Fabric",
    blurb: "Watch the machine. Not the Goal path. Governed routing and provider health.",
  },
  {
    href: "/control/health",
    slug: "health",
    label: "Health",
    title: "Portfolio health",
    blurb: "Pi-SEO scores — same family as sidebar Portfolio. Not a third health page.",
  },
  {
    href: "/control/roles",
    slug: "roles",
    label: "Roles",
    title: "Pipeline roles",
    blurb: "Watch the machine. Not the Goal path. Eight-phase roster.",
  },
  {
    href: "/control/build",
    slug: "build",
    label: "Build",
    title: "Run a build",
    blurb: "Engineer hatch. Not Goal. Start a session from a repo URL and a brief.",
  },
  {
    href: "/control/runs",
    slug: "runs",
    label: "Runs",
    title: "Routine runs",
    blurb: "Cron outcomes — same list as sidebar Routines.",
  },
  {
    href: "/control/curator",
    slug: "curator",
    label: "Curator",
    title: "Curator proposals",
    blurb: `${SPECIALIST_TILE_NOTE} Pending curator proposals.`,
  },
  {
    href: "/control/margot",
    slug: "margot",
    label: "Margot",
    title: "Margot assets",
    blurb: `${SPECIALIST_TILE_NOTE} Dry-run matrix and packets.`,
  },
  {
    href: "/control/pipeline",
    slug: "pipeline",
    label: "Pipeline",
    title: "Spec pipeline",
    blurb: `${SPECIALIST_TILE_NOTE} Machine spec pipeline status.`,
  },
  {
    href: "/control/terminal",
    slug: "terminal",
    label: "Terminal",
    title: "Terminal fleet",
    blurb: `${SPECIALIST_TILE_NOTE} Live redacted tmux panes.`,
  },
];

export const CONTROL_NAV: readonly ControlNavItem[] = [CONTROL_HUB, ...CONTROL_SECTIONS];

export function controlSectionBySlug(slug: string): ControlNavItem | undefined {
  return CONTROL_SECTIONS.find((item) => item.slug === slug);
}

export function isControlSectionSlug(slug: string): slug is ControlSectionSlug {
  return (CONTROL_SECTION_SLUGS as readonly string[]).includes(slug);
}

export function isSpecialistControlSlug(slug: string): boolean {
  return (SPECIALIST_CONTROL_SLUGS as readonly string[]).includes(slug);
}

export function controlTileKicker(slug: string, label: string): string {
  if (slug === "goal") return "Primary";
  if (isSpecialistControlSlug(slug)) return "Specialist";
  return label;
}
