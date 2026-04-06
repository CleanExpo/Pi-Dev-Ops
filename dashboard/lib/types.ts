export type Model = "opus" | "sonnet" | "haiku";

export type SessionStatus =
  | "created"
  | "cloning"
  | "building"
  | "complete"
  | "failed"
  | "killed";

export interface Session {
  id: string;
  repo: string;
  status: SessionStatus;
  started: number;
  lines: number;
}

export type LineType =
  | "phase"
  | "system"
  | "success"
  | "error"
  | "tool"
  | "agent"
  | "output"
  | "metric"
  | "stderr"
  | "done";

export interface OutputLine {
  type: LineType;
  text: string;
  ts: number;
}

export interface BuildRequest {
  repo_url: string;
  brief: string;
  model: Model;
}

export interface BuildResponse {
  session_id: string;
  status: SessionStatus;
}

export const TIER_INFO: Record<
  Model,
  { label: string; role: string; color: string; badge: string }
> = {
  opus: {
    label: "Orchestrator",
    role: "Plans, decomposes briefs, delegates",
    color: "#E8751A",
    badge: "Opus 4.6",
  },
  sonnet: {
    label: "Specialist",
    role: "Complex implementation & review",
    color: "#6B8CFF",
    badge: "Sonnet 4.6",
  },
  haiku: {
    label: "Worker",
    role: "Discrete task execution",
    color: "#4CAF82",
    badge: "Haiku 4.5",
  },
};
