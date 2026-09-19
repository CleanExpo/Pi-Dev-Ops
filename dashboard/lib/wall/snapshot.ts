/**
 * Live Wall snapshot — pure builder. Spec: docs/briefs/live-wall-v1.md.
 *
 * Nothing starts green. A machine is GREEN only when its own `last_seen` is present
 * and at most 60s old; the upstream `is_stale` flag is not trusted. Agents carry their
 * own 90s clock, so a crashed agent on a live machine still goes GREY. Every
 * mesh-derived value is self-reported and says so.
 *
 * Station chips stay GREY "NO LIVE SOURCE YET" until a reader for their outside
 * source (Linear, GitHub, production probe) is wired. No sample rows, ever.
 */
import { ageSeconds, isAbsent } from "./absent";

export type Chip = "GREEN" | "RED" | "GREY";

export const MACHINE_STALE_S = 60;
export const AGENT_STALE_S = 90;

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

export function machineTile(host: string, row: Record<string, unknown> | undefined, agents: unknown[], now: number): MachineTile {
  const base = { host, load1: null, selfReported: true as const, agents: [] as AgentTile[] };
  if (!row) return { ...base, chip: "GREY", reason: "never reported", ageSeconds: null };
  const age = ageSeconds(row.last_seen, now);
  const load = typeof row.load1 === "number" ? row.load1 : null;
  const mine = agents.map(record).filter((a): a is Record<string, unknown> => a !== null && a.machine === host);
  const tiles = mine.map((a) => agentTile(a, now));
  if (age === null) return { ...base, load1: load, agents: tiles, chip: "GREY", reason: "no usable last_seen (missing, garbled or in the future)", ageSeconds: null };
  const fresh = age <= MACHINE_STALE_S;
  return { ...base, load1: load, agents: tiles, chip: fresh ? "GREEN" : "GREY", reason: fresh ? "reporting" : "no signal", ageSeconds: age };
}

/** Build the fleet panel from the raw upstream body. `null` body = the read failed. */
export function fleetPanel(raw: unknown, hosts: string[], now: number, failure?: { kind: "broken" | "no_source"; reason: string }): FleetPanel {
  const grey = (status: FleetPanel["status"], reason: string): FleetPanel => ({
    status, reason, others: [], machines: hosts.map((h) => ({ ...machineTile(h, undefined, [], now), reason })),
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
  const machines = hosts.map((h) => machineTile(h, rows.get(h), agents, now));
  const others = [...rows.keys()].filter((h) => !hosts.includes(h)).sort();
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
