/**
 * The Live Wall's single definition of "absent" (spec docs/briefs/live-wall-v1.md §4).
 *
 * Every chip rule checks its inputs against this BEFORE any comparison runs, so a
 * missing timestamp can never make `criteria < first_commit` evaluate truthy.
 *
 * Absent means any of: missing key / undefined; null; empty or whitespace-only
 * string; empty array; empty object; or numeric 0 where the field is an identifier
 * or timestamp rather than a count.
 */
export function isAbsent(value: unknown, opts: { zeroIsAbsent?: boolean } = {}): boolean {
  if (value === undefined || value === null) return true;
  if (typeof value === "string") return value.trim() === "";
  if (typeof value === "number") return Number.isNaN(value) || (opts.zeroIsAbsent === true && value === 0);
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === "object") return Object.keys(value as object).length === 0;
  return false;
}

/** True when any named input is absent. Identifier/timestamp fields treat 0 as absent. */
export function anyAbsent(inputs: Record<string, unknown>): string | null {
  for (const [name, value] of Object.entries(inputs)) {
    if (isAbsent(value, { zeroIsAbsent: true })) return name;
  }
  return null;
}

/** Parse an ISO timestamp; absent or unparseable -> null, never "now" and never 0. */
export function parseTime(value: unknown): number | null {
  if (isAbsent(value) || typeof value !== "string") return null;
  const ms = Date.parse(value);
  return Number.isNaN(ms) ? null : ms;
}

/** Clock skew tolerated before a future timestamp is treated as garbled. */
export const FUTURE_SKEW_S = 5;

/**
 * Age in seconds, or null when the stamp is absent, unparseable, or more than
 * FUTURE_SKEW_S in the future. A future stamp must never read as "0s old": that
 * would keep a chip GREEN for as long as the clock stays ahead.
 */
export function ageSeconds(value: unknown, now: number): number | null {
  const t = parseTime(value);
  if (t === null) return null;
  const age = Math.round((now - t) / 1000);
  return age < -FUTURE_SKEW_S ? null : Math.max(0, age);
}
