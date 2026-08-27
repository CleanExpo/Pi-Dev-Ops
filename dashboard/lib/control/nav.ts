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
  blurb: "Throughput, Linear queue, sessions, and observability.",
};

export const CONTROL_SECTIONS: readonly ControlNavItem[] = [
  {
    href: "/control/goal",
    slug: "goal",
    label: "Goal",
    title: "Goal → Linear",
    blurb: "Select a project, draft Linear tickets from the goal, approve before Linear.",
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
    blurb: "Governed model routing, live provider health, failover and ZTE evidence.",
  },
  {
    href: "/control/health",
    slug: "health",
    label: "Health",
    title: "Portfolio health",
    blurb: "Pi-SEO health tiles and sparklines.",
  },
  {
    href: "/control/roles",
    slug: "roles",
    label: "Roles",
    title: "Pipeline roles",
    blurb: "Real 8-phase roster status.",
  },
  {
    href: "/control/build",
    slug: "build",
    label: "Build",
    title: "Run a build",
    blurb: "Start a session from a repo URL and a brief.",
  },
  {
    href: "/control/runs",
    slug: "runs",
    label: "Runs",
    title: "Routine runs",
    blurb: "Last routine executions.",
  },
  {
    href: "/control/curator",
    slug: "curator",
    label: "Curator",
    title: "Curator proposals",
    blurb: "Pending curator proposals.",
  },
  {
    href: "/control/margot",
    slug: "margot",
    label: "Margot",
    title: "Margot assets",
    blurb: "Dry-run matrix and packets.",
  },
  {
    href: "/control/pipeline",
    slug: "pipeline",
    label: "Pipeline",
    title: "Spec pipeline",
    blurb: "Machine spec pipeline status.",
  },
  {
    href: "/control/terminal",
    slug: "terminal",
    label: "Terminal",
    title: "Terminal fleet",
    blurb: "Live redacted tmux panes.",
  },
];

export const CONTROL_NAV: readonly ControlNavItem[] = [CONTROL_HUB, ...CONTROL_SECTIONS];

export function controlSectionBySlug(slug: string): ControlNavItem | undefined {
  return CONTROL_SECTIONS.find((item) => item.slug === slug);
}

export function isControlSectionSlug(slug: string): slug is ControlSectionSlug {
  return (CONTROL_SECTION_SLUGS as readonly string[]).includes(slug);
}
