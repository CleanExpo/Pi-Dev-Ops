/**
 * Server-side projection of GET /api/mesh/fleet for the Mission Control tile.
 *
 * The upstream snapshot is secret-bearing (X-Pi-CEO-Secret). This module
 * never sees the secret; it only maps a parsed body onto the four fields
 * the tile may show: revision, last heartbeat, current claim, plus the
 * BFF's own checkedAt. A missing or failed machines source is
 * `unavailable` — never an empty list that looks like "nobody enrolled".
 */

export interface FleetMachine {
  host: string;
  revision: string | null;
  lastHeartbeat: string | null;
  currentClaim: string | null;
  stale: boolean;
}

export interface FleetOk {
  status: "ok";
  checkedAt: string;
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

function machinesSourceFailed(errors: unknown): boolean {
  if (!Array.isArray(errors)) return false;
  return errors.some((entry) => asRecord(entry)?.source === "machines");
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
  return {
    host,
    revision: text(machine.version),
    lastHeartbeat: text(machine.last_seen),
    currentClaim: claimFor(host, claims),
    stale: machine.is_stale === true,
  };
}

/** Map an upstream fleet body onto the tile contract. */
export function projectFleet(raw: unknown, checkedAt: string): FleetView {
  const body = asRecord(raw);
  if (!body || !Array.isArray(body.machines)) {
    return { status: "unavailable", checkedAt, reason: "fleet snapshot missing" };
  }
  if (machinesSourceFailed(body.errors)) {
    return { status: "unavailable", checkedAt, reason: "machines source failed" };
  }
  const claims = Array.isArray(body.claims) ? body.claims : [];
  const machines = body.machines
    .map((row) => projectMachine(row, claims))
    .filter((row): row is FleetMachine => row !== null);
  return { status: "ok", checkedAt, machines };
}

export function unavailableFleet(reason: string, checkedAt: string): FleetUnavailable {
  return { status: "unavailable", checkedAt, reason };
}
