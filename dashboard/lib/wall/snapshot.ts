/**
 * Live Wall snapshot — pure builder. Spec: docs/briefs/live-wall-v1.md.
 *
 * Nothing starts green. A machine is GREEN only when its own `last_seen` is present
 * and at most 60s old AND its status is in HEALTHY_STATUSES; the upstream `is_stale`
 * flag is not trusted. A fresh machine the runner holds (quota, blocked, ...) is RED. Agents carry their
 * own 90s clock, so a crashed agent on a live machine still goes GREY. Every
 * mesh-derived value is self-reported and says so.
 *
 * Station chips stay GREY "NO LIVE SOURCE YET" until a reader for their outside
 * source (Linear, GitHub, production probe) is wired. No sample rows, ever.
 */
import { ageSeconds, isAbsent } from "./absent";

/**
 * The cloud claim row (app/server/session_lease.py CLOUD_CLAIM_MACHINE). Same value as
 * lib/control/mesh-fleet.ts CLOUD_CLAIM_HOST, which this page graph may not import
 * (__tests__/command-centre-readonly.test.ts); __tests__/wall-snapshot.test.ts pins the two equal.
 */
export const CLOUD_CLAIM_HOST = "railway";

export type Chip = "GREEN" | "RED" | "GREY";

export const MACHINE_STALE_S = 60;
export const AGENT_STALE_S = 90;

/**
 * The ONLY statuses that can be GREEN. An allow-list: a missing word, `updating`, or one the
 * runner adds later is never shown as healthy. mods/mission-control/hooks/fleet.ts holds the
 * same two sets; neither may import the other or the runner, so
 * tests/test_fleet_status_vocabulary.py pins both to mesh/heartbeat.py node_status().
 */
export const HEALTHY_STATUSES = new Set(["online", "working"]);
/** The runner gated itself: RED "held: <status>". Only picks the wording; health is HEALTHY_STATUSES. */
export const HELD_STATUSES = new Set(["blocked", "quarantined", "stuck", "quota", "outdated", "version-unknown", "hard_stop"]);
const DOWN_STATUSES = new Set(["runner-down", "offline"]);
const HOLD_REASON_MAX = 120;
const NO_HOLD_REASON = "reason not reported by this machine's heartbeat";

/** The three machines that make up the fleet. Override with WALL_FLEET_HOSTS (comma list). */
export const DEFAULT_FLEET_HOSTS = ["Phills-MacBook-Pro", "Phills-Mac-mini", "Phill_Desktop"];

export interface AgentTile { runtime: string; state: string; chip: Chip; ageSeconds: number | null }
export interface MachineTile {
  host: string;
  chip: Chip;
  reason: string;
  ageSeconds: number | null;
  load1: number | null;
  selfReported: true;
  agents: AgentTile[];
}
export interface FleetPanel {
  status: "ok" | "broken" | "no_source";
  reason: string;
  machines: MachineTile[];
  /** Hosts that reported but are not part of the declared fleet. Shown, not counted. */
  others: string[];
}
export interface Station { id: string; name: string; chip: Chip; reason: string }
export interface WallSnapshot {
  generated_at: string;
  banner: { red: number; grey: number };
  fleet: FleetPanel;
  stations: Station[];
}

const STATIONS: Array<[string, string, string]> = [
  ["capture", "Capture", "Linear reader: issue exists"],
  ["shape", "Shape", "Linear reader: falsifiable done-test in the description"],
  ["contract", "Contract", "Linear criteria time vs GitHub push-received time"],
  ["build", "Build", "GitHub reader: commit and PR for the ticket"],
  ["prove", "Prove", "GitHub CI for the head SHA AND the independent checker's run"],
  ["ship", "Ship", "a ticket-declared live probe at the production URL"],
  ["learn", "Learn", "Linear reader: SHIP-DELTA line on the ticket"],
];

function record(v: unknown): Record<string, unknown> | null {
  return v !== null && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

function agentTile(row: Record<string, unknown>, now: number): AgentTile {
  const age = ageSeconds(row.updated_at, now);
  const fresh = age !== null && age <= AGENT_STALE_S;
  return { runtime: String(row.runtime ?? "?"), state: String(row.state ?? "?"), chip: fresh ? "GREEN" : "GREY", ageSeconds: age };
}

/** hold_reason from a present `mesh-runner` entry of agent_runtimes (mesh/runner_report.py), else null. */
function holdReason(runtimes: unknown): string | null {
  if (!Array.isArray(runtimes)) return null;
  const entry = runtimes.map(record).find((e) => e?.runtime === "mesh-runner");
  if (!entry || entry.present !== true || typeof entry.hold_reason !== "string") return null;
  const text = entry.hold_reason.replace(/\s+/g, " ").trim().slice(0, HOLD_REASON_MAX);
  return text || null;
}

/** The chip and words for a machine whose heartbeat is fresh: its status decides. */
function freshChip(row: Record<string, unknown>): { chip: Chip; reason: string } {
  const status = typeof row.status === "string" ? row.status.trim() : "";
  if (HEALTHY_STATUSES.has(status)) return { chip: "GREEN", reason: "reporting" };
  if (HELD_STATUSES.has(status)) {
    const why = holdReason(row.agent_runtimes);
    return { chip: "RED", reason: why ? `held: ${status} — ${why}` : `held: ${status} (${NO_HOLD_REASON})` };
  }
  if (DOWN_STATUSES.has(status)) return { chip: "RED", reason: status };
  return { chip: "GREY", reason: `status ${status || "missing"}: not a healthy state` };
}

export function machineTile(host: string, row: Record<string, unknown> | undefined, agents: unknown[], now: number): MachineTile {
  const base = { host, load1: null, selfReported: true as const, agents: [] as AgentTile[] };
  if (!row) return { ...base, chip: "GREY", reason: "never reported", ageSeconds: null };
  const age = ageSeconds(row.last_seen, now);
  const load = typeof row.load1 === "number" ? row.load1 : null;
  const mine = agents.map(record).filter((a): a is Record<string, unknown> => a !== null && a.machine === host);
  const tiles = mine.map((a) => agentTile(a, now));
  if (age === null) return { ...base, load1: load, agents: tiles, chip: "GREY", reason: "no usable last_seen (missing, garbled or in the future)", ageSeconds: null };
  const fresh = age <= MACHINE_STALE_S;
  const shown = fresh ? freshChip(row) : { chip: "GREY" as const, reason: "no signal" };
  return { ...base, load1: load, agents: tiles, ...shown, ageSeconds: age };
}

/** Build the fleet panel from the raw upstream body. `null` body = the read failed. */
export function fleetPanel(raw: unknown, hosts: string[], now: number, failure?: { kind: "broken" | "no_source"; reason: string }): FleetPanel {
  // The cloud claim row is never a fleet machine, even when WALL_FLEET_HOSTS names it.
  const declared = hosts.filter((h) => h !== CLOUD_CLAIM_HOST);
  const grey = (status: FleetPanel["status"], reason: string): FleetPanel => ({
    status, reason, others: [], machines: declared.map((h) => ({ ...machineTile(h, undefined, [], now), reason })),
  });
  if (failure) return grey(failure.kind, failure.reason);
  const body = record(raw);
  if (!body || !Array.isArray(body.machines)) return grey("broken", "fleet snapshot missing");
  if (Array.isArray(body.errors) && body.errors.some((e) => record(e)?.source === "machines")) {
    return grey("broken", "machines source failed");
  }
  const rows = new Map<string, Record<string, unknown>>();
  for (const r of body.machines.map(record)) if (r && !isAbsent(r.host)) rows.set(String(r.host), r);
  const agents = Array.isArray(body.agents) ? body.agents : [];
  const machines = declared.map((h) => machineTile(h, rows.get(h), agents, now));
  // The cloud claim row is not a machine and nothing heartbeats it, so it is not "also reporting".
  const others = [...rows.keys()].filter((h) => !declared.includes(h) && h !== CLOUD_CLAIM_HOST).sort();
  return { status: "ok", reason: "", machines, others };
}

export function stations(): Station[] {
  return STATIONS.map(([id, name, feed]) => ({ id, name, chip: "GREY", reason: `NO LIVE SOURCE YET — needs ${feed}` }));
}

/** Count every chip on the wall. Always returns numbers, including zeros. */
export function bannerCounts(fleet: FleetPanel, st: Station[]): { red: number; grey: number } {
  const chips: Chip[] = [
    ...fleet.machines.flatMap((m) => [m.chip, ...m.agents.map((a) => a.chip)]),
    ...st.map((s) => s.chip),
  ];
  return { red: chips.filter((c) => c === "RED").length, grey: chips.filter((c) => c === "GREY").length };
}

export function buildSnapshot(fleet: FleetPanel, now: number): WallSnapshot {
  const st = stations();
  return { generated_at: new Date(now).toISOString(), banner: bannerCounts(fleet, st), fleet, stations: st };
}
