// fleet-guard — keeps subagents and agent-team teammates on allowed models and
// caps how many teammates run at once.
//
// Hooks `agent.spawn`, which fires before a subagent starts and, since Claude
// Code v2.1.289, before an agent-team teammate starts (e.isTeammate === true).
// The decisions are pure and live in hooks/fleet.ts.
//
// Configuration (environment, read on each spawn so a change applies at once):
//   FLEET_GUARD_MODELS         comma list of model ids or aliases, e.g. sonnet,haiku.
//                              A spawn on any other model is moved to the first one.
//   FLEET_GUARD_MAX_TEAMMATES  integer. A teammate spawn while that many teammates
//                              are live (pending, running, waiting or idle) is denied.
// Both unset: the mod changes nothing.
//
// If $.agent.list() fails the teammate count is unknown, and the spawn is
// allowed with one log line: a guard that cannot count must not deny blind.
//
// Functions that take `$` are top-level declarations: the engine scans the
// module before loading it and refuses `$` handed to anything else.

import type { EngineInterface, Register } from 'claude-code'
import { decide, liveTeammates, parseCap, parseModels, type Policy } from './fleet'

async function policy($: EngineInterface): Promise<Policy> {
  const models = parseModels(await $.env.get('FLEET_GUARD_MODELS'))
  const cap = parseCap(await $.env.get('FLEET_GUARD_MAX_TEAMMATES'))
  if (cap === 'invalid') {
    $.ui.log('fleet-guard: FLEET_GUARD_MAX_TEAMMATES is not a whole number; teammates are not capped')
    return { models, cap: null }
  }
  return { models, cap }
}

// The number of live teammates, or null when the list could not be read.
async function countLive($: EngineInterface): Promise<number | null> {
  try {
    return liveTeammates(await $.agent.list())
  } catch {
    $.ui.log('fleet-guard: teammate count unknown ($.agent.list failed); allowing this teammate')
    return null
  }
}

export const register: Register = on => {
  on('agent.spawn', async ($, e, next) => {
    const p = await policy($)
    if (p.models === null && p.cap === null) return next(e)
    const isTeammate = e.isTeammate === true
    const live = isTeammate && p.cap !== null ? await countLive($) : null
    const d = decide({ isTeammate, fork: e.fork, model: e.model, parentModel: e.parentModel }, p, live)
    if (d.kind === 'deny') return { deny: d.reason }
    if (d.kind === 'rewrite') {
      const who = isTeammate ? 'teammate' : 'subagent'
      $.ui.log(`fleet-guard: ${who} model ${d.from} is not in FLEET_GUARD_MODELS; using ${d.model}`)
      return next({ ...e, model: d.model })
    }
    return next(e)
  })
}
