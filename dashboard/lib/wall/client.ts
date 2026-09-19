/**
 * Live Wall browser-side rules. Spec: docs/briefs/live-wall-v1.md §5-6.
 *
 * The browser trusts the snapshot's own `generated_at`, never the HTTP status: a
 * cache whose updater died keeps answering 200 with the last good payload.
 */
import { parseTime } from "./absent";
import type { Chip, Station } from "./snapshot";

export const POLL_MS = 5_000;
export const STALE_AFTER_MS = POLL_MS * 3;

/** Seconds since the snapshot was generated, or null when the stamp is absent/garbled. */
export function snapshotAgeSeconds(generatedAt: unknown, now: number): number | null {
  const t = parseTime(generatedAt);
  return t === null ? null : Math.max(0, Math.round((now - t) / 1000));
}

/** Stale when the stamp is missing, unparseable, or older than three poll intervals. */
export function isSnapshotStale(generatedAt: unknown, now: number): boolean {
  const t = parseTime(generatedAt);
  return t === null || now - t > STALE_AFTER_MS;
}

/** A stale snapshot turns every chip GREY; a fresh one shows the chip as reported. */
export function displayChip(chip: Chip, stale: boolean): Chip {
  return stale ? "GREY" : chip;
}

/**
 * Stations the accordion rotates through: every non-GREEN station, RED first. A
 * station is skipped only when it is GREEN. When nothing is non-GREEN, rotate all.
 */
export function rotationOrder(stations: Station[]): string[] {
  const red = stations.filter((s) => s.chip === "RED").map((s) => s.id);
  const grey = stations.filter((s) => s.chip === "GREY").map((s) => s.id);
  const order = [...red, ...grey];
  return order.length ? order : stations.map((s) => s.id);
}

/** Next station id after `current` in the rotation, wrapping around. */
export function nextStation(order: string[], current: string | null): string | null {
  if (!order.length) return null;
  const i = current === null ? -1 : order.indexOf(current);
  return order[(i + 1) % order.length];
}

/** Match the kiosk `?machine=` param to a fleet host, case-insensitively. */
export function resolveKioskMachine(param: string | null, hosts: string[]): { host: string | null; unknown: boolean } {
  if (!param || !param.trim()) return { host: null, unknown: false };
  const hit = hosts.find((h) => h.toLowerCase() === param.trim().toLowerCase());
  return hit ? { host: hit, unknown: false } : { host: null, unknown: true };
}
