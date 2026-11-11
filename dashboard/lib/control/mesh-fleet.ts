/**
 * Server-side projection of GET /api/mesh/fleet for the Mission Control tile.
 *
 * The upstream snapshot is secret-bearing (X-Pi-CEO-Secret). This module
 * never sees the secret; it only maps a parsed body onto the four fields
 * the tile may show: revision, last heartbeat, current claim, plus the
 * BFF's own checkedAt. A missing or failed machines source is
 * `unavailable` — never an empty list that looks like "nobody enrolled".
 * A failed claims source is `claimsAvailable: false` — never "claim none".
 *
 * Fleet version gate (08/11/2026): each heartbeat carries one `mesh-runner`
 * entry in `agent_runtimes` (mesh/runner_report.py) with the runner's code,
 * the approved code, its hold and its last update and job. It is projected as
 * `runner`; a missing entry or field is null, shown as "unknown", never guessed.
 */

/**
 * The shared cloud claim row (app/server/session_lease.py CLOUD_CLAIM_MACHINE).
 * Every cloud replica claims under it and nothing heartbeats it, so upstream
 * `is_stale` is true by design. It is labelled, never shown as a stale machine.
 */
export const CLOUD_CLAIM_HOST = "railway";

export interface RunnerEvent {
  outcome: string | null;
  /** Unix seconds. */
  ts: number | null;
}

export interface RunnerJob {
  linearId: string | null;
  state: string | null;
  /** Unix seconds. */
  ts: number | null;
}

/** The heartbeat's `mesh-runner` entry. Every field is null when the runner did not say. */
export interface RunnerView {
  version: string | null;
  approvedVersion: string | null;
  versionStatus: string | null;
  state: string | null;
  stateAgeS: number | null;
  currentTask: string | null;
  holdReason: string | null;
  localEdits: number | null;
  lastUpdate: RunnerEvent | null;
  lastJob: RunnerJob | null;
}

export interface FleetMachine {
  host: string;
  /** The node status the heartbeat derived (working, online, outdated, hard_stop, runner-down, ...). */
  status: string | null;
  revision: string | null;
  lastHeartbeat: string | null;
  currentClaim: string | null;
  stale: boolean;
  /** The CLOUD_CLAIM_HOST row: never heartbeats, so never stale. */
  placeholder: boolean;
  runner: RunnerView | null;
}

export interface FleetOk {
  status: "ok";
  checkedAt: string;
  /**
   * False when the upstream `claims` source failed (mesh_fleet.py reports it in
   * `errors`). Every `currentClaim` is then unknown, never "no claim".
   */
  claimsAvailable: boolean;
  machines: FleetMachine[];
}

export interface FleetUnavailable {
  status: "unavailable";
  checkedAt: string;
  reason: string;
}

export type FleetView = FleetOk | FleetUnavailable;

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function count(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function projectRunner(runtimes: unknown): RunnerView | null {
  if (!Array.isArray(runtimes)) return null;
  const row = runtimes.map(asRecord).find((entry) => entry?.runtime === "mesh-runner" && entry.present === true);
  if (!row) return null;
  const update = asRecord(row.last_update);
  const job = asRecord(row.last_job);
  return {
    version: text(row.version),
    approvedVersion: text(row.approved_version),
    versionStatus: text(row.version_status),
    state: text(row.state),
    stateAgeS: count(row.state_age_s),
    currentTask: text(row.current_task),
    holdReason: text(row.hold_reason),
    localEdits: count(row.local_edits),
    lastUpdate: update ? { outcome: text(update.outcome), ts: count(update.ts) } : null,
    lastJob: job ? { linearId: text(job.linear_id), state: text(job.state), ts: count(job.ts) } : null,
  };
}

const BLOCKED = new Set(["blocked", "quarantined", "stuck", "quota"]);

/**
 * The state the tile shows. Read from the heartbeat's own status, never inferred:
 * a stale heartbeat is offline; working is busy; online is idle; a gate hold names its gate.
 * updating, outdated, version-unknown, runner-down and hard_stop are shown as sent.
 */
export function displayState(machine: Pick<FleetMachine, "status" | "stale">): string {
  if (machine.stale) return "offline";
  const status = machine.status;
  if (!status) return "unknown";
  if (status === "working") return "busy";
  if (status === "online") return "idle";
  if (status === "blocked") return "blocked";
  return BLOCKED.has(status) ? `blocked (${status})` : status;
}

function sourceFailed(errors: unknown, source: string): boolean {
  if (!Array.isArray(errors)) return false;
  return errors.some((entry) => asRecord(entry)?.source === source);
}

function claimFor(host: string, claims: unknown[]): string | null {
  for (const entry of claims) {
    const row = asRecord(entry);
    if (row && row.machine === host) return text(row.linear_id);
  }
  return null;
}

function projectMachine(row: unknown, claims: unknown[]): FleetMachine | null {
  const machine = asRecord(row);
  const host = text(machine?.host);
  if (!machine || !host) return null;
  const placeholder = host === CLOUD_CLAIM_HOST;
  return {
    host,
    status: text(machine.status),
    revision: text(machine.version),
    lastHeartbeat: text(machine.last_seen),
    currentClaim: claimFor(host, claims),
    stale: !placeholder && machine.is_stale === true,
    placeholder,
    runner: projectRunner(machine.agent_runtimes),
  };
}

/** Map an upstream fleet body onto the tile contract. */
export function projectFleet(raw: unknown, checkedAt: string): FleetView {
  const body = asRecord(raw);
  if (!body || !Array.isArray(body.machines)) {
    return { status: "unavailable", checkedAt, reason: "fleet snapshot missing" };
  }
  if (sourceFailed(body.errors, "machines")) {
    return { status: "unavailable", checkedAt, reason: "machines source failed" };
  }
  // A failed claims read arrives as `claims: []` plus an errors entry. Reading
  // only the list turned it into "claim none" on every machine.
  const claimsAvailable = Array.isArray(body.claims) && !sourceFailed(body.errors, "claims");
  const claims = claimsAvailable ? (body.claims as unknown[]) : [];
  const machines = body.machines
    .map((row) => projectMachine(row, claims))
    .filter((row): row is FleetMachine => row !== null);
  return { status: "ok", checkedAt, claimsAvailable, machines };
}

export function unavailableFleet(reason: string, checkedAt: string): FleetUnavailable {
  return { status: "unavailable", checkedAt, reason };
}
