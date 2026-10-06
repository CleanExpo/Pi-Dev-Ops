// Pure decisions for fleet-guard: no `$`, so they unit-test without the kit.
//
// Two rules on every `agent.spawn` (a subagent, or an agent-team teammate when
// e.isTeammate is true):
//   models  FLEET_GUARD_MODELS, a comma list of model ids or aliases. A spawn
//           whose model (the one it asked for, else its parent's) matches none
//           is rewritten to the first entry. Unset or empty: every model passes.
//   cap     FLEET_GUARD_MAX_TEAMMATES, an integer. A teammate spawn while that
//           many teammates are already live is denied. Subagents are never
//           capped. Unset: no cap.

/** Agent states that hold a teammate's resources: started and not yet ended. */
export const LIVE_STATES: ReadonlySet<string> = new Set(['pending', 'running', 'waiting', 'idle'])

/** The allow list, lower-cased, or null when unset or empty (the rule is off). */
export function parseModels(raw: string | undefined): string[] | null {
  if (raw === undefined) return null
  const list = raw.split(',').map(s => s.trim().toLowerCase()).filter(s => s.length > 0)
  return list.length > 0 ? list : null
}

/** The cap, null when unset or empty, or 'invalid' for anything but a whole number ≥ 0. */
export function parseCap(raw: string | undefined): number | null | 'invalid' {
  if (raw === undefined || raw.trim() === '') return null
  const t = raw.trim()
  return /^\d+$/.test(t) ? Number(t) : 'invalid'
}

/**
 * True when `model` is on the list: the same id or alias, or an id that has the
 * alias as one of its dash-separated words (`claude-sonnet-5-5` matches
 * `sonnet`). An alias asked for is never taken to match a full id on the list,
 * because which id the alias resolves to is the host's choice, not ours.
 */
export function modelAllowed(model: string, allowed: readonly string[]): boolean {
  const m = model.trim().toLowerCase()
  const words = m.split(/[-_.:/\s[\]]+/)
  return allowed.some(a => a === m || words.includes(a))
}

/** How many live teammates a `$.agent.list()` answer holds. Subagents are not counted. */
export function liveTeammates(agents: readonly { teammateId?: string; status: string }[]): number {
  return agents.filter(a => a.teammateId !== undefined && LIVE_STATES.has(a.status)).length
}

export type SpawnFacts = {
  isTeammate: boolean
  fork: boolean
  /** The model the spawn asked for (alias or id), if any. */
  model?: string
  /** The parent's effective model: what a spawn that names none runs on. */
  parentModel: string
}

export type Policy = {
  models: string[] | null
  cap: number | null
}

export type Decision =
  | { kind: 'pass' }
  | { kind: 'deny'; reason: string }
  | { kind: 'rewrite'; model: string; from: string }

/**
 * What to do with one spawn. `live` is the number of live teammates, or null
 * when it could not be counted (then the cap is not applied: never deny blind).
 */
export function decide(spawn: SpawnFacts, policy: Policy, live: number | null): Decision {
  if (spawn.isTeammate && policy.cap !== null && live !== null && live >= policy.cap) {
    return { kind: 'deny', reason: `fleet-guard: ${live} teammates already running (cap ${policy.cap})` }
  }
  // A fork always runs on its parent's model and ignores `model`, so there is nothing to rewrite.
  if (policy.models === null || spawn.fork) return { kind: 'pass' }
  const asked = spawn.model && spawn.model.toLowerCase() !== 'inherit' ? spawn.model : spawn.parentModel
  if (modelAllowed(asked, policy.models)) return { kind: 'pass' }
  return { kind: 'rewrite', model: policy.models[0] as string, from: asked }
}
