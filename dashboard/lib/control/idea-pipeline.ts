export const IDEA_VERDICTS = ["PROMOTE", "BACKLOG", "PARK", "KILL"] as const;

export type IdeaVerdict = (typeof IDEA_VERDICTS)[number];

export interface IdeaPacket {
  idea_id: string;
  text: string;
  source: string;
  status: string;
  verdict: string | null;
  recommended_verdict: string;
  go_at: string | null;
  executed: boolean;
  execution_requested?: boolean;
  north_star_fit: { label: string; score: number; rationale: string };
  effort_vs_impact: { effort: string; impact: string; rationale: string };
  directive: { label: string; rationale: string };
  displacement: { would_displace: string; rationale: string };
  judge: { score: number; decision: string; note?: string };
  spm: { problem: string; desired_outcome: string; out_of_scope: string };
  /** Set when a mesh node reviewed this idea from an idea:plan Linear ticket. */
  linear_id?: string;
  /** The node's gs-autoplan Board packet, markdown shown as plain text. */
  plan_packet_md?: string | null;
}

export interface IdeaSnapshot {
  intake: string;
  north_star: string;
  awaiting: number;
  packet: IdeaPacket | null;
  verdicts: string[];
  go_required: boolean;
  executed: boolean;
}

export interface IdeaPipelinePayload {
  snapshot: IdeaSnapshot;
  packets?: IdeaPacket[];
}

export function canAuthorizeGo(packet: IdeaPacket | null): boolean {
  return Boolean(packet && packet.verdict === "PROMOTE" && !packet.go_at);
}

export function disposeFeedback(verdict: string): string {
  if (verdict === "PROMOTE") {
    return "Parked as PROMOTE. Nothing has started. Press GO if this should be allowed to run later.";
  }
  return `Recorded as ${verdict}. Nothing has started.`;
}
