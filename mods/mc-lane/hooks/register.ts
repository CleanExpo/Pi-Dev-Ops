// mc-lane — reports this Claude Code lane to Mission Control.
//
// Spec: docs/specs/claude-mods-integration.md §3.1 (telemetry only; no controls).
// Server: POST /api/mesh/lane-events (app/server/routes/mesh_lane_events.py).
//
// Runs in interactive sessions, `claude -p` and Agent SDK lanes alike: mods'
// hooks load in all three (docs/reference/claude-mods/overview.md, "Where mods
// run"). Nothing here draws, so a headless lane loses nothing.
//
// Configuration (environment, read at each session.start):
//   MC_LANE_URL     Pi-CEO backend base URL, e.g. https://pi-dev-ops.up.railway.app
//   MC_LANE_SECRET  the X-Pi-CEO-Secret the fleet already uses for heartbeats
//   MC_LANE_HOST    this machine's fleet name (as in mesh_machines.host)
// With URL or secret unset the mod records nothing and says so once in the
// transcript: an unconfigured lane must read as "not reporting", never as idle.
//
// HOT RELOAD. Every reload re-runs `register` and `session.start`, resets the
// module variables and cancels the timers (docs/reference/claude-mods/api.md,
// interface.md "Keep state"). So what must survive one — the unsent queue, the
// counter, and whether this session's `session_start` was already recorded —
// lives in `$.state` (declared in types/index.d.ts). What must survive the
// session itself is parked in `$.store` at session.end. `/clear`, `/resume` and
// `/branch` reset `$.state` too; events still unsent at that moment (at most one
// flush interval's worth while the backend answers) are lost, not duplicated.
//
// Functions that take `$` are top-level declarations: the engine scans the
// module before loading it and refuses `$` handed to anything else.

import type { EngineInterface, Register } from 'claude-code'
import { atom, read, update } from 'claude-code'
import {
  dropAcked, enqueue, makeSeq, MAX_BATCH, modelName, repoSlug, toolName, worstRate,
  type LaneEvent, type LaneEventKind,
} from './lane'

const FLUSH_MS = 5_000
const PENDING = 'pending:'

type Config = { url: string; secret: string; host: string }

// Session state: survives a reload of this module.
const queue = atom({ plugin: 'mc-lane', key: 'queue' } as const, [] as LaneEvent[])
const counter = atom({ plugin: 'mc-lane', key: 'counter' } as const, 0)
/** The session whose `session_start` is recorded; '' until then. */
const started = atom({ plugin: 'mc-lane', key: 'started' } as const, '')

// Module state: rebuilt by every session.start, so a reload loses nothing here.
const st = {
  sessionId: 'unknown',
  cfg: null as Config | null,
  flushing: false, // the flush timer of this module instance is running
  inFlight: false,
  lastFailure: undefined as string | undefined,
}

function append(events: LaneEvent[]): (q: LaneEvent[]) => LaneEvent[] {
  return q => {
    const next = q.slice()
    for (const ev of events) enqueue(next, ev)
    return next
  }
}

async function record($: EngineInterface, kind: LaneEventKind, extra: Partial<LaneEvent>): Promise<void> {
  const now = await $.clock.now()
  const n = await update($, counter, c => c + 1)
  const ev: LaneEvent = {
    session_id: st.sessionId,
    seq: makeSeq(now, n),
    kind,
    at: new Date(now).toISOString(),
    ...extra,
  }
  await update($, queue, append([ev]))
}

// One POST at a time; a tick that lands while one is out is skipped.
async function flush($: EngineInterface): Promise<void> {
  const cfg = st.cfg
  if (!cfg || st.inFlight) return
  const pending = await read($, queue)
  if (pending.length === 0) return
  st.inFlight = true
  const batch = pending.slice(0, MAX_BATCH)
  let failure: string | undefined
  try {
    const r = await $.http.fetch(`${cfg.url}/api/mesh/lane-events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Pi-CEO-Secret': cfg.secret },
      body: JSON.stringify({ host: cfg.host, events: batch }),
    })
    if (r.ok) {
      const acked = (JSON.parse(r.text) as { acked?: Record<string, number> }).acked ?? {}
      // Drops only what was acked: events recorded during the POST stay.
      await update($, queue, q => dropAcked(q, acked))
    } else {
      failure = `HTTP ${r.status}`
    }
  } catch (err) {
    failure = err instanceof Error ? err.message.slice(0, 80) : 'request failed'
  } finally {
    st.inFlight = false
  }
  if (failure !== st.lastFailure) {
    // Only on change, so a long outage is one status line, not one per tick.
    const left = (await read($, queue)).length
    $.ui.status(failure ? `Mission Control unreachable (${failure}); ${left} queued` : undefined)
    st.lastFailure = failure
  }
}

export const register: Register = on => {
  // Before the first prompt, and again after every reload of this module.
  on('session.start', async ($, e, next) => {
    const url = (await $.env.get('MC_LANE_URL'))?.replace(/\/+$/, '')
    const secret = await $.env.get('MC_LANE_SECRET')
    const host = (await $.env.get('MC_LANE_HOST')) || 'unknown'
    st.sessionId = await $.session.id()

    if (!url || !secret) {
      st.cfg = null
      $.ui.log('not reporting to Mission Control: MC_LANE_URL or MC_LANE_SECRET is unset')
      return next(e)
    }
    st.cfg = { url, secret, host }

    // Events a previous session on this machine could not send before it ended.
    for (const key of await $.store.keys()) {
      if (!key.startsWith(PENDING)) continue
      const saved = await $.store.get(key)
      if (Array.isArray(saved)) await update($, queue, append(saved as LaneEvent[]))
      await $.store.delete(key)
    }

    // A reload re-runs this hook in the same session: record its start once.
    if ((await read($, started)) !== st.sessionId) {
      const repo = await $.session.repo()
      const model = await $.session.model()
      await record($, 'session_start', { repo: repoSlug(repo?.remote), model: modelName(model) })
      await update($, started, () => st.sessionId)
    }

    // A reload cancelled the previous instance's timer; this instance starts its own once.
    if (!st.flushing) {
      st.flushing = true
      $.clock.every(FLUSH_MS, () => flush($))
    }
    return next(e)
  })

  on('tool.call', async ($, e, next) => {
    if (!st.cfg) return next(e)
    const t0 = await $.clock.now()
    const ran = await next(e)
    const ms = Math.max(0, (await $.clock.now()) - t0)
    // A denied call never ran: recorded as not ok, with no timing.
    const denied = ran.deny !== undefined
    await record($, 'tool', { tool: toolName(e.tool), ok: !denied && ran.isError !== true, ms: denied ? undefined : ms })
    return ran
  })

  // Subagents and agent-team teammates (e.isTeammate). Passed through as given;
  // only the agent type's name and the model it started on are recorded.
  on('agent.spawn', async ($, e, next) => {
    const ran = await next(e)
    if (st.cfg && ran.deny === undefined) {
      await record($, 'agent_start', {
        model: modelName(ran.model),
        tool: e.subagentType ? toolName(e.subagentType) : undefined,
        ok: true,
      })
    }
    return ran
  })

  on('session.measure', async ($, e, next) => {
    if (st.cfg) {
      await record($, 'usage', {
        ctx_pct: e.context.percent,
        rate_pct: worstRate(e.rateLimits),
        // Absent where the host keeps no cost ledger: sent as absent, shown as unknown.
        cost_usd: e.cost?.usd,
      })
    }
    return next(e)
  })

  on('session.end', async ($, e, next) => {
    if (st.cfg) {
      await record($, 'session_end', {})
      // session.end hooks share ~1.5 s; there is no time to POST. Park what is
      // left for the next session on this machine to send.
      const left = await read($, queue)
      if (left.length > 0) await $.store.set(PENDING + st.sessionId, left)
      await update($, queue, () => [])
    }
    return next(e)
  })
}
