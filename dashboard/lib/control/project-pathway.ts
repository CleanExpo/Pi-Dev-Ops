export interface PipelineSummary {
  pipeline_id: string;
  repo_url: string;
  current_phase: string;
  phases_completed: string[];
  updated_at: string;
}

export const PATHWAY = [
  { label: "Idea", phase: null },
  { label: "Discovery", phase: "spec" },
  { label: "Plan", phase: "plan" },
  { label: "Build", phase: "build" },
  { label: "Test", phase: "test" },
  { label: "Audit", phase: "review" },
  { label: "Release", phase: "ship" },
  { label: "Live", phase: null },
] as const;

function repoKey(value: string): string | null {
  const trimmed = value.trim();
  const match = trimmed.match(/^(?:https?:\/\/github\.com\/|git@github\.com:)?([\w.-]+\/[\w.-]+?)(?:\.git|\/)?$/i);
  return match ? match[1].toLowerCase() : null;
}

export function latestPipelineForRepo(repo: string, summaries: PipelineSummary[]): PipelineSummary | null {
  const key = repoKey(repo);
  if (!key) return null;
  return summaries
    .filter((item) => item && typeof item.repo_url === "string" && repoKey(item.repo_url) === key)
    .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))[0] ?? null;
}

export function stageEvidence(label: typeof PATHWAY[number]["label"], pipeline: PipelineSummary | null): string {
  if (!pipeline) return "unverified";
  if (label === "Idea") return "pipeline recorded";
  if (label === "Live") return "unverified";
  const phase = PATHWAY.find((item) => item.label === label)?.phase;
  return phase && pipeline.phases_completed?.includes(phase) ? "completed" : "unverified";
}
