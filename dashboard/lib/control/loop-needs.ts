// "Needs me" — the Loop Cockpit's list of things waiting on a human.
//
// Extracted from app/(main)/loop/page.tsx so it is unit-testable on its own and
// so that page stays under the 300-line convention.
//
// The observability entries are OBJECTS, not strings. They were typed `string[]`
// and pushed straight into a rendered child, so React threw on the one list whose
// entire job is telling the founder what needs him.
//
// "Nothing needs you" is only true when every read below succeeded. Three review
// rounds each found one more failed read that leaked through as the all-clear,
// so availability is now a required record with one entry per source, and an
// entry that is missing or anything but an explicit null fails closed.

import { unavailableReason, type MCAction, type MissionControlLive } from "@/lib/control/mission-control-live";

export type { MCAction };

/** Every read the "Needs me" all-clear depends on. */
export const NEEDS_SOURCES = ["live", "autonomy", "swarm", "routines", "queue", "sessionStore", "observability"] as const;
export type NeedsSource = (typeof NEEDS_SOURCES)[number];
/** Per source: `null` = the read succeeded; a string = why it failed. */
export type NeedsAvailability = Record<NeedsSource, string | null>;

export interface AutonomyRead {
  enabled: boolean;
  stale: boolean;
  poller_iteration_errors: number;
  last_iteration_error: string | null;
}

export interface SwarmRead { kill_switch_active: boolean; escalation_lock_active: boolean }

export interface NeedsInputs {
  availability: NeedsAvailability;
  autonomy?: AutonomyRead | null;
  swarm?: SwarmRead | null;
  actions?: MCAction[];
  nextIssueId?: string | null;
}

export interface NeedItem {
  text: string;
  color: string;
}

const ERROR = "var(--error)";
const WARNING = "var(--warning)";
const MUTED = "var(--text-muted)";

const UNAVAILABLE: Record<NeedsSource, (reason: string) => string> = {
  live: (r) => `Mission Control live read unavailable — queue, sessions and alerts unknown (${r})`,
  autonomy: () => "Autonomy status unavailable — poller state unknown",
  swarm: () => "Swarm status unavailable — kill-switch state unknown",
  routines: () => "Loop runs unavailable — recent loop runs unknown",
  queue: (r) => `Linear queue unavailable — ${r}`,
  sessionStore: () => "Session store unavailable — running work is unknown",
  observability: () => "Observability unavailable — component alerts unknown",
};

/** Sections of the live payload: when the live read itself failed, its need covers them. */
const PART_OF_LIVE: ReadonlySet<NeedsSource> = new Set(["queue", "sessionStore", "observability"]);

const obj = (v: unknown): Record<string, unknown> | null =>
  v !== null && typeof v === "object" ? (v as Record<string, unknown>) : null;

/** A body that does not report the poller's state is not a read of it. */
export function isAutonomyRead(v: unknown): v is AutonomyRead {
  const o = obj(v);
  return !!o && typeof o.enabled === "boolean" && typeof o.stale === "boolean"
    && typeof o.poller_iteration_errors === "number";
}

/** A body that does not report the kill-switch is not a read of it. */
export function isSwarmRead(v: unknown): v is SwarmRead {
  const o = obj(v);
  return !!o && typeof o.kill_switch_active === "boolean" && typeof o.escalation_lock_active === "boolean";
}

export function isRoutinesRead(v: unknown): boolean {
  return Array.isArray(obj(v)?.runs);
}

const NOT_READ = "the backend did not answer";

interface LoopReads { live: MissionControlLive | null; autonomy: unknown; swarm: unknown; routines: unknown }

/** One availability entry per source, from what the page actually fetched. */
export function loopAvailability({ live, autonomy, swarm, routines }: LoopReads): NeedsAvailability {
  const liveDown = !live ? NOT_READ : live.error ? live.error : null;
  const sessionsRead = !!live && Array.isArray(live.active_sessions) && Array.isArray(live.recent_completions)
    && Array.isArray(live.throughput?.hourly);
  return {
    live: liveDown,
    autonomy: isAutonomyRead(autonomy) ? null : NOT_READ,
    swarm: isSwarmRead(swarm) ? null : NOT_READ,
    routines: isRoutinesRead(routines) ? null : NOT_READ,
    queue: liveDown ?? unavailableReason(live?.queue),
    sessionStore: liveDown ?? (sessionsRead ? null : "a session-store read failed"),
    observability: liveDown ?? (Array.isArray(live?.observability?.actions) ? null : "not reported by the backend"),
  };
}

/** Why `source` is unavailable, or null. Anything but an explicit null fails closed. */
function downReason(availability: Partial<NeedsAvailability> | undefined, source: NeedsSource): string | null {
  const v = availability?.[source];
  if (v === null) return null;
  return typeof v === "string" && v ? v : "not reported";
}

/** One observability row rendered as a single actionable sentence. */
export function actionToNeed(a: MCAction): NeedItem {
  const what = a.next_action || `${a.component ?? "component"} is ${a.status ?? "not observed"}`;
  const which = a.component ? `${a.component}: ` : "";
  const who = a.owner ? ` — owner: ${a.owner}` : "";
  return {
    text: `${which}${what}${who}`,
    color: a.severity === "high" ? ERROR : WARNING,
  };
}

/** Flags from reads that succeeded. Callers pass null for a read that did not. */
function stateNeeds(autonomy: AutonomyRead | null, swarm: SwarmRead | null): NeedItem[] {
  const needs: NeedItem[] = [];
  if (swarm?.kill_switch_active)
    needs.push({ text: "Kill-switch is ACTIVE — autonomous work is paused", color: ERROR });
  if (swarm?.escalation_lock_active)
    needs.push({ text: "Escalation lock is active — awaiting approver", color: WARNING });
  if (autonomy && autonomy.enabled && autonomy.stale)
    needs.push({ text: "Autonomy poller is stale (>15m since last poll)", color: WARNING });
  if (autonomy && !autonomy.enabled)
    needs.push({ text: "Autonomy poller is disabled (TAO_AUTONOMY_ENABLED=0)", color: WARNING });
  if (autonomy && autonomy.poller_iteration_errors > 0)
    needs.push({
      text:
        `Poller has ${autonomy.poller_iteration_errors} iteration error(s)` +
        (autonomy.last_iteration_error ? `: ${autonomy.last_iteration_error}` : ""),
      color: ERROR,
    });
  return needs;
}

export function deriveNeeds({ availability, autonomy, swarm, actions, nextIssueId }: NeedsInputs): NeedItem[] {
  const needs: NeedItem[] = [];

  // A failed read is never an all-clear: every source gets an error-level need
  // unless its read succeeded.
  const liveDown = downReason(availability, "live");
  for (const source of NEEDS_SOURCES) {
    const reason = downReason(availability, source);
    if (reason && !(liveDown && PART_OF_LIVE.has(source)))
      needs.push({ text: UNAVAILABLE[source](reason), color: ERROR });
  }

  needs.push(...stateNeeds(
    downReason(availability, "autonomy") ? null : autonomy ?? null,
    downReason(availability, "swarm") ? null : swarm ?? null,
  ));

  if (!liveDown) for (const a of actions ?? []) needs.push(actionToNeed(a));

  if (nextIssueId) needs.push({ text: `Next queued ticket: ${nextIssueId}`, color: MUTED });

  return needs;
}
