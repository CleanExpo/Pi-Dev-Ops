// RA-7898 — payload shapes the converted panels and their feeds share.
//
// These were local interfaces inside each panel. They moved here unchanged so
// the panel and its feed reader agree on one definition.

import type { ProviderCockpitPayload } from "@/lib/command-centre/provider-usage";

export type FabricLane = { model: string; banned: boolean; models?: string[] };
export type FabricLastCall = {
  ts: number;
  role: string;
  lane: string;
  requested_model: string;
  served_model: string;
  provider: string;
  latency_ms: number;
  ok: boolean;
  attempts: string[];
  strengthened?: boolean;
  error?: string | null;
};
export type FabricStatus = {
  enabled: boolean;
  healthy: boolean;
  base_url?: string;
  allowed_roles?: string[];
  lanes?: Record<string, FabricLane>;
  strength_model?: string;
  models_available?: number;
  last_call?: FabricLastCall | null;
  totals?: { calls: number; failures: number; fallbacks?: number; strengthened?: number };
  blocked?: string[];
  error?: string | null;
};

export interface SwarmStatus {
  state: "SHADOW" | "ACTIVE" | "RATE_LIMITED" | "OFF" | "UNKNOWN";
  autonomous_prs_today: number | null;
  autonomous_prs_limit: number | null;
  green_merges: number | null;
  green_merges_target: number | null;
  last_pr_ts: string | null;
  last_pr_url: string | null;
}

/** SwarmPanel kept `data` and `error` apart: a failed read nulls the data. */
export interface SwarmValue {
  data: SwarmStatus | null;
  error: string | null;
}

export interface KillSwitchStatus {
  swarm_enabled_env?: boolean;
  kill_switch_active?: boolean;
  escalation_lock_active?: boolean;
  panic_count_last_hour?: number;
  approver_allowlist?: string[];
  approver_totp_configured?: string[];
  error?: string;
}

export interface ProposalRow {
  proposal_id?: string;
  ts: string;
  cluster_id?: string;
  trigger_source?: string;
  cluster_summary?: string;
  evidence_count?: number;
  proposed_skill_name?: string;
  status: string;
  draft_id?: string;
  reason?: string;
}

export interface CuratorValue {
  total?: number;
  returned?: number;
  by_status?: Record<string, number>;
  proposals?: ProposalRow[];
  error?: string;
}

export type ProviderUsageValue = ProviderCockpitPayload | null;

export interface WikiGraphSummary {
  pageCount: number | null;
  edgeCount: number | null;
  lastSync: string | null;
  source: string | null;
  reason: string | null;
}
