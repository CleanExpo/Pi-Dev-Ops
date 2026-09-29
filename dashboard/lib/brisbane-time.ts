// lib/brisbane-time.ts — every time the dashboard shows is Brisbane time.
//
// Without an explicit zone, toLocaleString() uses whatever machine renders it:
// Vercel's servers run on UTC, so server-rendered times and the first paint of
// the top-bar clock read 10 hours behind the founder's clock, and the browser
// then re-renders with its own zone (a hydration mismatch). Pinning the zone
// makes server and browser agree. Brisbane has no daylight saving, so it is
// always AEST (UTC+10).

export const BRISBANE_TZ = "Australia/Brisbane";
export const BRISBANE_LABEL = "AEST";
const LOCALE = "en-AU";

type Stamp = Date | string | number;

function toDate(value: Stamp): Date {
  return value instanceof Date ? value : new Date(value);
}

/** "14:05" or, with seconds, "14:05:09" — 24-hour Brisbane time. */
export function brisbaneTime(value: Stamp, withSeconds = false): string {
  return toDate(value).toLocaleTimeString(LOCALE, {
    timeZone: BRISBANE_TZ,
    hour: "2-digit",
    minute: "2-digit",
    ...(withSeconds ? { second: "2-digit" } : {}),
    hourCycle: "h23",
  });
}

/** "29 Sept, 14:05" — short date and time, Brisbane. */
export function brisbaneDateTime(value: Stamp): string {
  return toDate(value).toLocaleString(LOCALE, {
    timeZone: BRISBANE_TZ,
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
}
