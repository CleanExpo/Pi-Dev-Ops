// Presentation helpers for the CEO Command Centre overview.
//
// Extracted from app/(main)/overview/page.tsx when that file was edited, per
// the CLAUDE.md file-length convention: the page is over the 300-line
// convention and grandfathered, so touching it means extracting rather than
// adding. Pure formatting — no state, no fetching, no React.

export function formatUptime(s: number): string {
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
  return `${Math.floor(s / 86400)}d ${Math.floor((s % 86400) / 3600)}h`;
}

export function repoShort(repo: string): string {
  try {
    const parts = new URL(repo).pathname.replace(/^\//, "").split("/");
    return parts.slice(0, 2).join("/");
  } catch {
    return repo.replace(/^https?:\/\/[^/]+\//, "").slice(0, 40);
  }
}

export function skillFromPhase(phase?: string): string {
  if (!phase) return "Initialising";
  const map: Record<string, string> = {
    clone: "Checkout",
    build: "Code Review",
    scan: "Security Scan",
    test: "QA",
    evaluate: "ZTE Eval",
    ship: "Deploy",
    push: "Git Push",
  };
  for (const [key, label] of Object.entries(map)) {
    if (phase.toLowerCase().includes(key)) return label;
  }
  return phase;
}

export function swarmChip(health: {
  swarm_enabled?: boolean;
  swarm_shadow?: boolean;
} | null): { label: string; color: string } {
  if (!health || health.swarm_enabled === undefined) {
    return { label: "—", color: "var(--text-dim)" };
  }
  if (!health.swarm_enabled) return { label: "Off", color: "var(--error)" };
  if (health.swarm_shadow) return { label: "Shadow", color: "var(--warning)" };
  return { label: "Active", color: "var(--success)" };
}

export function overviewLede(health: {
  uptime_s?: number;
  sessions?: unknown;
  swarm_enabled?: boolean;
  autonomy?: unknown;
} | null): string {
  if (!health) return "Backend not reached. These tiles are not a live reading.";
  const measured = (
    health.uptime_s !== undefined
    || health.sessions !== undefined
    || health.swarm_enabled !== undefined
    || health.autonomy !== undefined
  );
  if (!measured) {
    return "Backend answered without measurements. Dashes are unknown, not zero.";
  }
  return "Live system overview · refreshes every 15s";
}

export function claudeCliChip(health: { claude_cli?: boolean } | null): { value: string; color: string } {
  if (!health || health.claude_cli === undefined) {
    return { value: "—", color: "var(--text-dim)" };
  }
  if (health.claude_cli) return { value: "OK", color: "var(--success)" };
  return { value: "Missing", color: "var(--error)" };
}

export type ServiceMark = "ok" | "off" | "unknown";

export function serviceMark(value: boolean | undefined): ServiceMark {
  if (value === undefined) return "unknown";
  return value ? "ok" : "off";
}

export function serviceMarkGlyph(mark: ServiceMark): { glyph: string; color: string } {
  if (mark === "ok") return { glyph: "✓", color: "var(--success)" };
  if (mark === "off") return { glyph: "✗", color: "var(--error)" };
  return { glyph: "—", color: "var(--text-dim)" };
}

export function overviewServiceRows(health: {
  claude_cli?: boolean;
  anthropic_key?: boolean;
  linear_key?: boolean;
  vercel_token?: boolean;
  autonomy?: { armed?: boolean };
} | null): Array<{ label: string; mark: ServiceMark }> {
  return [
    { label: "Claude CLI", mark: serviceMark(health?.claude_cli) },
    { label: "Anthropic API Key", mark: serviceMark(health?.anthropic_key) },
    { label: "Linear API Key", mark: serviceMark(health?.linear_key) },
    { label: "Vercel Token", mark: serviceMark(health?.vercel_token) },
    { label: "Autonomy Loop", mark: serviceMark(health?.autonomy?.armed) },
  ];
}

export const OVERVIEW_QUICK_LINKS = [
  { label: "Goal → Linear", href: "/control/goal" },
  { label: "Run a build", href: "/control/build" },
  { label: "Watch Builds", href: "/builds" },
  { label: "Analysis history", href: "/history" },
] as const;

export function statusDot(status: string): string {
  if (["cloning", "building", "evaluating"].includes(status)) return "var(--accent)";
  if (status === "complete" || status === "done") return "var(--success)";
  if (status === "failed" || status === "error") return "var(--error)";
  return "var(--text-dim)";
}
