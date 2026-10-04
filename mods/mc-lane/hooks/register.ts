// mc-lane — reports this Claude Code lane to Mission Control.
//
// Spec: docs/specs/claude-mods-integration.md §3.1 (telemetry only; no controls).
// Server: POST /api/mesh/lane-events (app/server/routes/mesh_lane_events.py).
//
// Runs in interactive sessions, `claude -p` and Agent SDK lanes alike: mods'
// hooks load in all three (docs/reference/claude-mods/overview.md, "Where mods
// run"). Nothing here draws, so a headless lane loses nothing.
//
// Configuration (environment, read once per load):
//   MC_LANE_URL     Pi-CEO backend base URL, e.g. https://pi-dev-ops.up.railway.app
//   MC_LANE_SECRET  the X-Pi-CEO-Secret the fleet already uses for heartbeats
//   MC_LANE_HOST    this machine's fleet name (as in mesh_machines.host)
// With URL or secret unset the mod records nothing and says so once in the
// transcript: an unconfigured lane must read as "not reporting", never as idle.
//
// Functions that take `$` are top-level declarations: the engine scans the
// module before loading it and refuses `$` handed to anything else.

import type { EngineInterface, Register } from 'claude-code'
import {
  dropAcked, enqueue, makeSeq, MAX_BATCH, repoSlug, toolName, worstRate,
  type LaneEvent, type LaneEventKind,
} from './lane'

const FLUSH_MS = 5_000
const PENDING = 'pending:'

type Config = { url: string; secret: string; host: string }

// Module state. A reload starts it over; the host-held $.store carries what must survive.
const st = {
  queue: [] as LaneEvent[],
  counter: 0,
  sessionId: 'unknown',
  cfg: null as Config | null,
  inFlight: false,
  lastFailure: undefined as string | undefined,
}

async function record($: EngineInterface, kind: LaneEventKind, extra: Partial<LaneEvent>): Promise<void> {
  const now = await $.clock.now()
  st.counter += 1
  enqueue(st.queue, {
    session_id: st.sessionId,
    seq: makeSeq(now, st.counter),
    kind,
    at: new Date(now).toISOString(),
    ...extra,
  })
}

// One POST at a time; a tick that lands while one is out is skipped.
async function flush($: EngineInterface): Promise<void> {
  const cfg = st.cfg
  if (!cfg || st.inFlight || st.queue.length === 0) return
  st.inFlight = true
  const batch = st.queue.slice(0, MAX_BATCH)
  let failure: string | undefined
  try {
    const r = await $.http.fetch(`${cfg.url}/api/mesh/lane-events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Pi-CEO-Secret': cfg.secret },
      body: JSON.stringify({ host: cfg.host, events: batch }),
    })
    if (r.ok) {
      const acked = (JSON.parse(r.text) as { acked?: Record<string, number> }).acked ?? {}
      st.queue = dropAcked(st.queue, acked)
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
    $.ui.status(failure ? `Mission Control unreachable (${failure}); ${st.queue.length} queued` : undefined)
    st.lastFailure = failure
  }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const url = (await $.env.get('MC_LANE_URL'))?.replace(/\/+$/, '')
    const secret = await $.env.get('MC_LANE_SECRET')
    const host = (await $.env.get('MC_LANE_HOST')) || 'unknown'
    st.sessionId = await $.session.id()

    if (!url || !secret) {
      $.ui.log('not reporting to Mission Control: MC_LANE_URL or MC_LANE_SECRET is unset')
      return next(e)
    }
    st.cfg = { url, secret, host }

    // Events a previous session on this machine could not send before it ended.
    for (const key of await $.store.keys()) {
      if (!key.startsWith(PENDING)) continue
      const saved = await $.store.get(key)
      if (Array.isArray(saved)) for (const ev of saved as LaneEvent[]) enqueue(st.queue, ev)
      await $.store.delete(key)
    }

    const repo = await $.session.repo()
    const model = await $.session.model()
    await record($, 'session_start', { repo: repoSlug(repo?.remote), model })

    $.clock.every(FLUSH_MS, () => flush($))
    return next(e)
  })

  on('tool.call', async ($, e, next) => {
    if (!st.cfg) return next(e)
    const started = await $.clock.now()
    const ran = await next(e)
    const ms = Math.max(0, (await $.clock.now()) - started)
    // A denied call never ran: recorded as not ok, with no timing.
    const denied = ran.deny !== undefined
    await record($, 'tool', { tool: toolName(e.tool), ok: !denied && ran.isError !== true, ms: denied ? undefined : ms })
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
      if (st.queue.length > 0) await $.store.set(PENDING + st.sessionId, st.queue)
      st.queue = []
    }
    return next(e)
  })
}
