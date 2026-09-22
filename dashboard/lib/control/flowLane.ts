export type FlowLane = "flow" | "engineer" | "founder" | "unclassified";

export interface LaneRules {
  founderPaths: string[];
  founderLabels: string[];
  engineerPaths: string[];
  engineerLabels: string[];
}

/** Starting list from UNI-2639 / .github/lanes.yml. Path list is proposed. */
export const DEFAULT_LANE_RULES: LaneRules = {
  founderPaths: [
    ".github/lanes.yml",
    ".github/CODEOWNERS",
    ".github/workflows/audit-receipt.yml",
    ".github/workflows/lane-gate.yml",
    "**/*.env*",
    "**/secrets/**",
    "**/pricing/**",
    "**/legal/**",
  ],
  founderLabels: ["lane:founder", "money", "public", "secrets", "legal"],
  engineerPaths: [
    "app/server/auth.py",
    "app/server/config.py",
    "dashboard/middleware.ts",
  ],
  engineerLabels: ["lane:engineer"],
};

export function rulesReadable(rules: LaneRules): boolean {
  return rules.founderPaths.length > 0 && rules.founderLabels.length > 0;
}

function safeRepoPath(path: string): boolean {
  return Boolean(
    path
    && path.length < 512
    && !path.includes("\0")
    && !path.includes("\\")
    && !path.includes("..")
    && !path.startsWith("/")
  );
}

function globish(path: string, pattern: string): boolean {
  if (!safeRepoPath(path) || !pattern || pattern === "**" || pattern.includes("\0")) return false;
  if (pattern === path) return true;
  const escaped = pattern
    .replace(/[.+^${}()|[\]\\]/g, "\\$&")
    .replace(/\*\*/g, ":::GLOBSTAR:::")
    .replace(/\*/g, "[^/]*")
    .replace(/:::GLOBSTAR:::/g, ".*");
  return new RegExp(`^${escaped}$`).test(path);
}

function pathHits(paths: string[], patterns: string[]): boolean {
  return paths.some((path) => patterns.some((pattern) => globish(path, pattern)));
}

function labelHits(labels: string[], wanted: string[]): boolean {
  const set = new Set(labels.map((item) => item.toLowerCase()));
  return wanted.some((item) => set.has(item.toLowerCase()));
}

function hasExplicitLane(labels: string[]): boolean {
  return labels.some((item) => item.toLowerCase().startsWith("lane:"));
}

/**
 * FOUNDER wins, then ENGINEER, then FLOW.
 * A label may raise a lane, never lower it.
 * No paths and no lane:* label → unclassified (never pretend FLOW).
 * Unreadable rules → unclassified.
 */
export function classifyLane(
  paths: string[],
  labels: string[],
  rules: LaneRules = DEFAULT_LANE_RULES,
): FlowLane {
  if (!rulesReadable(rules)) return "unclassified";
  const cleanPaths = paths.filter(safeRepoPath);
  const cleanLabels = labels.filter((item) => /^[a-z0-9:._-]{1,64}$/i.test(item));
  if (cleanPaths.length === 0 && !hasExplicitLane(cleanLabels)) return "unclassified";
  const founder = pathHits(cleanPaths, rules.founderPaths) || labelHits(cleanLabels, rules.founderLabels);
  if (founder) return "founder";
  const engineer = pathHits(cleanPaths, rules.engineerPaths) || labelHits(cleanLabels, rules.engineerLabels);
  if (engineer) return "engineer";
  if (labelHits(cleanLabels, ["lane:flow"]) || cleanPaths.length > 0) return "flow";
  return "unclassified";
}

export function agingTone(ageDays: number): "ok" | "watch" | "red" | "kill" {
  if (!Number.isFinite(ageDays) || ageDays < 0) return "kill";
  if (ageDays >= 7) return "kill";
  if (ageDays >= 5) return "red";
  if (ageDays >= 3) return "watch";
  return "ok";
}

export function flowBoardColumn(input: {
  lane: FlowLane;
  mergedToday: boolean;
  auditGreen: boolean;
  founderGo: boolean;
  ageDays: number;
}): "shipped" | "audit" | "phill" | "aging" {
  if (input.mergedToday && input.auditGreen && input.lane !== "unclassified") return "shipped";
  if (!Number.isFinite(input.ageDays) || input.ageDays < 0 || input.ageDays >= 5) return "aging";
  if (input.lane === "unclassified") return "audit";
  if (input.lane === "founder" && !input.founderGo) return "phill";
  if (input.lane === "founder" && input.founderGo) return "audit";
  return "audit";
}
