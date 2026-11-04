// Mission Control command wall — pure derivations for the /control wall screens.
//
// Truth rules (docs/plans/mission-control-visual-overhaul-2026-09-29.md):
// - a failed read is "unavailable", never 0 or an all-clear;
// - nothing is "live" unless its own source said so; scan scores are never progress;
// - a hop or panel with no reader is "not connected", never a sample value.

import type { FleetMachine, FleetView } from "@/lib/control/mesh-fleet";
import type { MCAction, MCObservability, MCQueue } from "@/lib/control/mission-control-live";
import type { FlowBoardPayload } from "@/lib/control/flowBoard";
import type { CiValue, Field, PullsValue } from "@/lib/control/card-truth";
import type { KillSwitchStatus, SourceState } from "@/lib/boards/sources";
import type { MachineTile, WallSnapshot } from "@/lib/wall/snapshot";

export type Tone = "ok" | "warn" | "bad" | "idle";

/** Friendly names for the three declared fleet hosts (lib/wall/snapshot.ts DEFAULT_FLEET_HOSTS). */
const HOST_NAMES: Record<string, string> = {
  "Phills-MacBook-Pro": "MacBook",
  "Phills-Mac-mini": "Mac Mini",
  Phill_Desktop: "PC",
};

export function hostLabel(host: string): string {
  return HOST_NAMES[host] ?? host;
}

export interface FleetScreenTile {
  host: string;
  label: string;
  tone: Tone;
  status: string;
  ageSeconds: number | null;
  load1: number | null;
  /** Agent runtimes the machine itself reports, with their own freshness. */
  agents: { runtime: string; state: string; fresh: boolean }[];
  /** The ticket the mesh says this machine holds; null = none, undefined = claims unreadable. */
  claim: string | null | undefined;
}

function claimFor(host: string, fleet: FleetView | null): string | null | undefined {
  if (!fleet || fleet.status !== "ok" || fleet.claimsAvailable !== true) return undefined;
  const row = fleet.machines.find((m: FleetMachine) => m.host === host);
  return row ? row.currentClaim ?? null : null;
}

function tileTone(machine: MachineTile): Tone {
  if (machine.chip === "RED") return "bad";
  if (machine.chip === "GREEN") return "ok";
  return machine.ageSeconds === null ? "idle" : "warn";
}

/** One tile per declared machine. A missing wall snapshot yields no tiles (the panel says why). */
export function fleetTiles(wall: WallSnapshot | null, fleet: FleetView | null): FleetScreenTile[] {
  if (!wall) return [];
  return wall.fleet.machines.map((m) => ({
    host: m.host,
    label: hostLabel(m.host),
    tone: tileTone(m),
    status: m.chip === "GREEN" ? "heartbeat fresh" : m.reason,
    ageSeconds: m.ageSeconds,
    load1: m.load1,
    agents: m.agents.map((a) => ({ runtime: a.runtime, state: a.state, fresh: a.chip === "GREEN" })),
    claim: claimFor(m.host, fleet),
  }));
}

/** "42 s", "3 min", "2 h", "4 d"; "never" when unknown. */
export function ageText(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) return "never";
  if (seconds < 60) return `${Math.round(seconds)} s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  if (seconds < 86_400) return `${Math.round(seconds / 3600)} h`;
  return `${Math.round(seconds / 86_400)} d`;
}

/** What /api/flow-board?repo= returns: the board plus its two card fields. */
export interface RepoBoard extends FlowBoardPayload {
  repo: string;
  pull_requests: Field<PullsValue>;
  ci: Field<CiValue>;
}

export interface PrRow {
  repo: string;
  name: string;
  /** Null = the read failed; never shown as zero. */
  open: number | null;
  capped: boolean;
  /** Flow-board "audit" column: a label classification, not review activity. */
  auditLane: number | null;
  needsPhill: number | null;
  aging: number | null;
  ci: { tone: Tone; text: string };
  /** Why main-branch CI could not be read; null when it was read. */
  ciReason: string | null;
  /** Why the pull requests could not be read; null when they were read. */
  reason: string | null;
}

const CI_TEXT: Record<CiValue["state"], [Tone, string]> = {
  success: ["ok", "passing"],
  failure: ["bad", "failing"],
  error: ["bad", "error"],
  pending: ["warn", "running"],
  expected: ["warn", "waiting"],
  none: ["idle", "no checks"],
};

export function prRow(repo: string, board: RepoBoard | null | undefined, readFailure?: string | null): PrRow {
  const name = repo.split("/")[1] ?? repo;
  const ci = board?.ci.status === "ok"
    ? { tone: CI_TEXT[board.ci.value.state][0], text: CI_TEXT[board.ci.value.state][1] }
    : { tone: "idle" as Tone, text: "unavailable" };
  const ciReason = board?.ci.status === "unavailable" ? board.ci.reason : board ? null : readFailure ?? null;
  if (!board || board.pull_requests.status !== "ok" || !board.ok) {
    const reason = !board ? readFailure ?? "not read yet"
      : board.pull_requests.status === "unavailable" ? board.pull_requests.reason : board.error ?? "board read failed";
    return { repo, name, open: null, capped: false, auditLane: null, needsPhill: null, aging: null, ci, ciReason, reason };
  }
  const c = board.columns;
  return {
    repo, name, ci, ciReason, reason: null,
    open: board.pull_requests.value.count,
    capped: board.pull_requests.value.capped,
    auditLane: c.audit.length,
    needsPhill: c.phill.length,
    aging: c.aging.length,
  };
}

export interface Alert {
  id: string;
  tone: Tone;
  text: string;
}

function observabilityAlerts(obs: MCObservability | undefined): Alert[] {
  if (!obs) return [];
  const red = (obs.red_components ?? []).map((c) => ({ id: `red-${c}`, tone: "bad" as Tone, text: `${c} is red` }));
  const degraded = (obs.degraded_components ?? []).map((c) => ({ id: `deg-${c}`, tone: "warn" as Tone, text: `${c} is degraded` }));
  const actions = (obs.actions ?? [])
    .filter((a: MCAction) => a.ok === false && a.next_action)
    .map((a: MCAction, i) => ({ id: `act-${a.component ?? i}`, tone: "warn" as Tone, text: `${a.component ?? "component"}: ${a.next_action}` }));
  return [...red, ...degraded, ...actions];
}

function queueAlerts(queue: MCQueue | undefined): Alert[] {
  if (!queue) return [];
  if (queue.available === false) return [{ id: "queue-down", tone: "warn", text: `Linear queue unreadable: ${queue.error ?? "no reason given"}` }];
  return (queue.urgent ?? 0) > 0 ? [{ id: "queue-urgent", tone: "bad", text: `${queue.urgent} urgent ticket(s) in the queue` }] : [];
}

/** Unreadable PR or CI evidence is an alert. A repo still on its first read is not. */
function githubAlerts(p: PrRow): Alert[] {
  const out: Alert[] = [];
  if (p.open === null && p.reason && p.reason !== "not read yet") {
    out.push({ id: `pr-${p.repo}`, tone: "warn", text: `${p.name} pull requests unavailable: ${p.reason}` });
  }
  if (p.ciReason && p.ciReason !== p.reason) {
    out.push({ id: `cidown-${p.repo}`, tone: "warn", text: `${p.name} main branch CI unavailable: ${p.ciReason}` });
  }
  return out;
}

export interface AlertInputs {
  sources: { id: string; label: string; state: SourceState; reason: string | null }[];
  observability?: MCObservability;
  queue?: MCQueue;
  killSwitch?: KillSwitchStatus | null;
  fleet: FleetScreenTile[];
  prs: PrRow[];
}

/** Every alert the connected sources support, worst first. Failed sources are alerts themselves. */
export function deriveAlerts(input: AlertInputs): Alert[] {
  const sourceAlerts = input.sources
    .filter((s) => s.state === "unreachable" || s.state === "stale" || s.state === "no_source")
    .map((s) => ({
      id: `src-${s.id}`,
      tone: (s.state === "unreachable" ? "bad" : "warn") as Tone,
      text: `${s.label} ${s.state === "no_source" ? "not connected" : s.state}${s.reason ? `: ${s.reason}` : ""}`,
    }));
  const kill = input.killSwitch?.kill_switch_active
    ? [{ id: "kill", tone: "bad" as Tone, text: "Kill switch is ACTIVE: autonomous work is halted" }] : [];
  const fleet = input.fleet.filter((t) => t.tone !== "ok")
    .map((t) => ({ id: `fleet-${t.host}`, tone: t.tone === "bad" ? "bad" as Tone : "warn" as Tone, text: `${t.label}: ${t.status} (last heartbeat ${ageText(t.ageSeconds)} ago)` }));
  const ci = input.prs.filter((p) => p.ci.tone === "bad")
    .map((p) => ({ id: `ci-${p.repo}`, tone: "bad" as Tone, text: `${p.name} main branch CI ${p.ci.text}` }));
  const github = input.prs.flatMap((p) => githubAlerts(p));
  const all = [...kill, ...observabilityAlerts(input.observability), ...queueAlerts(input.queue), ...ci, ...github, ...fleet, ...sourceAlerts];
  const rank: Record<Tone, number> = { bad: 0, warn: 1, idle: 2, ok: 3 };
  return all.sort((a, b) => rank[a.tone] - rank[b.tone]);
}

export interface FlowHop {
  id: string;
  label: string;
  detail: string;
  connected: boolean;
}

/**
 * CRM -> Synthex campaign flow. No reader exists for any hop between the CRM and
 * Synthex yet, so every hop is "not connected". The two end nodes show only their
 * repository's main-branch CI, labelled as code health, never as campaign status.
 */
export const CAMPAIGN_HOPS: readonly FlowHop[] = [
  { id: "lead", label: "Lead captured in CRM", detail: "needs a CRM lead-event reader", connected: false },
  { id: "handoff", label: "Hand-off to Synthex", detail: "needs a CRM to Synthex hand-off log", connected: false },
  { id: "build", label: "Campaign built", detail: "needs a Synthex campaign-state reader", connected: false },
  { id: "publish", label: "Published", detail: "needs a channel publish receipt", connected: false },
  { id: "results", label: "Results back to CRM", detail: "needs an attribution feed", connected: false },
];

export const CRM_REPO = "CleanExpo/CCW-CRM";
export const SYNTHEX_REPO = "CleanExpo/Synthex";

/** The repos whose PR pipeline the wall shows, most active first. */
export const WALL_REPOS: readonly string[] = [
  "CleanExpo/Pi-Dev-Ops",
  "CleanExpo/RestoreAssist",
  "CleanExpo/Synthex",
  "CleanExpo/carsi",
  "CleanExpo/unite-group",
  "CleanExpo/CCW-CRM",
];
