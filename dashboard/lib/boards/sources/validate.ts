// RA-7898 — payload checks for the direct feeds.
//
// A 200 may count as live only when it carries every field its panel reads,
// in the type the panel reads it as. Anything less is a failed read: a
// missing field must never render as an invented "0", "no" or "DISABLED",
// and a wrong-typed field must never reach a panel that would crash on it.
// Each check mirrors the type in shapes.ts, lib/wall/snapshot.ts or
// lib/control/mesh-fleet.ts, which is what the backend always sends.

import type { WallSnapshot } from "@/lib/wall/snapshot";
import { record } from "./http";
import type { CuratorValue, FabricStatus, KillSwitchStatus, SwarmValue } from "./shapes";

const isText = (v: unknown) => typeof v === "string";
const isNum = (v: unknown) => typeof v === "number" && Number.isFinite(v);
const isBool = (v: unknown) => typeof v === "boolean";
const isTextOrNull = (v: unknown) => v === null || isText(v);
const isNumOrNull = (v: unknown) => v === null || isNum(v);
const optText = (v: unknown) => v === undefined || isTextOrNull(v);
const optNum = (v: unknown) => v === undefined || isNumOrNull(v);
const isTextList = (v: unknown) => Array.isArray(v) && v.every(isText);
const optTextList = (v: unknown) => v === undefined || isTextList(v);
const isChip = (v: unknown) => v === "GREEN" || v === "RED" || v === "GREY";
const isCount = (v: unknown) => v === null || (isNum(v) && (v as number) >= 0);
const every = (v: unknown, check: (x: Record<string, unknown>) => boolean) =>
  Array.isArray(v) && v.every((x) => { const r = record(x); return r !== null && check(r); });

/** mesh-fleet: FleetMachine rows. */
export const isFleetMachines = (v: unknown) => every(v, (m) => isText(m.host) && isBool(m.stale)
  && isTextOrNull(m.revision) && isTextOrNull(m.lastHeartbeat) && isTextOrNull(m.currentClaim));

const isAgent = (a: Record<string, unknown>) => isText(a.runtime) && isText(a.state) && isChip(a.chip) && isNumOrNull(a.ageSeconds);
const isWallMachine = (m: Record<string, unknown>) => isText(m.host) && isChip(m.chip) && isText(m.reason)
  && isNumOrNull(m.ageSeconds) && isNumOrNull(m.load1) && every(m.agents, isAgent);
const isStation = (s: Record<string, unknown>) => isText(s.id) && isText(s.name) && isChip(s.chip) && isText(s.reason);

/** wall: the whole WallSnapshot, whatever the fleet status - a failed fleet still renders its panel. */
export function isWallSnapshot(b: Record<string, unknown>): b is Record<string, unknown> & WallSnapshot {
  const fleet = record(b.fleet);
  const banner = record(b.banner);
  return isText(b.generated_at) && banner !== null && isNum(banner.red) && isNum(banner.grey)
    && fleet !== null && (fleet.status === "ok" || fleet.status === "broken" || fleet.status === "no_source")
    && isText(fleet.reason) && every(fleet.machines, isWallMachine) && isTextList(fleet.others)
    && every(b.stations, isStation);
}

const isLane = (l: Record<string, unknown>) => isText(l.model) && isBool(l.banned) && optTextList(l.models);
const isLastCall = (c: Record<string, unknown>) => isNum(c.ts) && isText(c.role) && isText(c.lane)
  && isText(c.requested_model) && isText(c.served_model) && isText(c.provider) && isNum(c.latency_ms)
  && isBool(c.ok) && isTextList(c.attempts) && (c.strengthened === undefined || isBool(c.strengthened)) && optText(c.error);

/** model-fabric: model_fabric.status_snapshot always sends all of these. */
export function isFabricStatus(b: FabricStatus): boolean {
  const t = record(b.totals);
  const lanes = record(b.lanes);
  const last = b.last_call === undefined || b.last_call === null ? null : record(b.last_call);
  return isBool(b.enabled) && isBool(b.healthy) && isNum(b.models_available)
    && t !== null && isNum(t.calls) && isNum(t.failures) && isNum(t.fallbacks) && isNum(t.strengthened)
    && lanes !== null && every(Object.values(lanes), isLane)
    && (b.last_call === undefined || b.last_call === null || (last !== null && isLastCall(last)))
    && optText(b.strength_model) && optTextList(b.blocked) && optTextList(b.allowed_roles) && optText(b.base_url);
}

const SWARM_STATES = new Set<unknown>(["SHADOW", "ACTIVE", "RATE_LIMITED", "OFF", "UNKNOWN"]);

/** swarm-status: app/api/swarm-status/route.ts always sends all seven. */
export function isSwarmStatus(d: NonNullable<SwarmValue["data"]>): boolean {
  return SWARM_STATES.has(d.state) && isCount(d.autonomous_prs_today) && isCount(d.autonomous_prs_limit)
    && isCount(d.green_merges) && isCount(d.green_merges_target)
    && isTextOrNull(d.last_pr_ts) && isTextOrNull(d.last_pr_url);
}

/** kill-switch: routes/swarm.py always sends all six. */
export function isKillSwitchStatus(b: KillSwitchStatus): boolean {
  return isBool(b.kill_switch_active) && isBool(b.swarm_enabled_env) && isBool(b.escalation_lock_active)
    && isNum(b.panic_count_last_hour) && isTextList(b.approver_allowlist) && isTextList(b.approver_totp_configured);
}

const isProposal = (p: Record<string, unknown>) => isText(p.ts) && optText(p.status) && optText(p.proposal_id)
  && optText(p.cluster_id) && optText(p.trigger_source) && optText(p.cluster_summary)
  && optText(p.proposed_skill_name) && optText(p.draft_id) && optText(p.reason) && optNum(p.evidence_count);

const isPlan = (p: Record<string, unknown>) => isText(p.id) && isText(p.label) && isText(p.state)
  && isNumOrNull(p.usagePct) && isText(p.truthLevel);
const isProvider = (p: Record<string, unknown>) => isText(p.id) && isText(p.label) && isText(p.planType)
  && isText(p.resetCadence) && isText(p.state) && isText(p.truthLevel) && isText(p.bestUseLane)
  && isTextOrNull(p.fallbackProvider) && isTextOrNull(p.missingSetupReason) && isNumOrNull(p.usagePct)
  && isText(p.lastChecked) && (p.plans === undefined || every(p.plans, isPlan));
const isRoute = (r: Record<string, unknown>) => isText(r.lane) && isTextOrNull(r.recommended) && isText(r.reason);

/** provider-usage: the whole ProviderCockpitPayload (lib/command-centre/provider-usage.ts). */
export function isProviderUsage(b: Record<string, unknown>): boolean {
  const s = record(b.summary);
  return isText(b.generatedAt) && s !== null
    && ["total", "available", "watching", "nearLimit", "blocked", "unknown"].every((k) => isNum(s[k]))
    && every(b.providers, isProvider) && every(b.routing, isRoute);
}

/** curator: routes/swarm.py always sends by_status counts and ProposalRow rows. */
export function isCuratorList(b: CuratorValue): boolean {
  const counts = record(b.by_status);
  return counts !== null && Object.values(counts).every(isNum) && every(b.proposals, isProposal);
}
