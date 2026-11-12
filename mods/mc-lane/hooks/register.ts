// mc-lane — reports this Claude Code lane to Mission Control.
//
// Spec: docs/specs/claude-mods-integration.md §3.1 (telemetry only; no controls).
// Server: POST /api/mesh/lane-events (app/server/routes/mesh_lane_events.py).
//
// Runs in interactive sessions, `claude -p` and Agent SDK lanes alike: mods'
// hooks load in all three (docs/reference/claude-mods/overview.md, "Where mods
// run"). Nothing here draws, so a headless lane loses nothing.
//
// Configuration (read at each session.start; lane_config.ts says why and how):
//   MC_LANE_URL     Pi-CEO backend base URL, e.g. https://pi-dev-ops.up.railway.app
//   MC_LANE_SECRET  the X-Pi-CEO-Secret the fleet already uses for heartbeats
//   MC_LANE_HOST    this machine's fleet name (as in mesh_machines.host)
// From this process's environment, else from launchd (`/bin/launchctl getenv`), with
// URL and secret as a pair from one place. With neither place holding both the mod
// records nothing, says so once in the transcript (by setting name only), and looks
// again every RETRY_MS: an app that started before the launch agent starts
// reporting once launchd has the settings. Unconfigured must read as "not
// reporting", never as idle.
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
import {
  clean, fromLaunchctl, launchctlArgv, LAUNCHCTL_TIMEOUT_MS, notConfiguredDetail, pickLaneConfig,
  type LaneConfig, type LaneVars, type LaunchdRead,
} from './lane_config'

const FLUSH_MS = 5_000
const RETRY_MS = 30_000
const PENDING = 'pending:'

type Config = LaneConfig

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
  retry: null as { cancel(): void } | null, // looks for the settings again while unconfigured
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

async function launchdValue($: EngineInterface, name: string): Promise<string | undefined> {
  return fromLaunchctl(await $.process.run(launchctlArgv(name), { timeoutMs: LAUNCHCTL_TIMEOUT_MS }))
}

async function readLaunchd($: EngineInterface): Promise<LaunchdRead> {
  try {
    return {
      vars: {
        url: await launchdValue($, 'MC_LANE_URL'),
        secret: await launchdValue($, 'MC_LANE_SECRET'),
        host: await launchdValue($, 'MC_LANE_HOST'),
      },
    }
  } catch (err) {
    return { error: err instanceof Error ? err.name : 'error' }
  }
}

/** Environment first; launchd only when the environment lacks the pair. */
async function resolveLane($: EngineInterface): Promise<{ cfg: Config } | { why: string }> {
  const env: LaneVars = {
    url: clean(await $.env.get('MC_LANE_URL')),
    secret: clean(await $.env.get('MC_LANE_SECRET')),
    host: clean(await $.env.get('MC_LANE_HOST')),
  }
  const fromEnv = pickLaneConfig(env, null)
  if (fromEnv) return { cfg: fromEnv }
  const launchd = await readLaunchd($)
  const cfg = 'vars' in launchd ? pickLaneConfig(env, launchd.vars) : null
  return cfg ? { cfg } : { why: notConfiguredDetail(env, launchd) }
}

// The retry tick: once launchd holds the settings, start reporting and stop looking.
async function retryLane($: EngineInterface): Promise<void> {
  if (st.cfg) return
  const res = await resolveLane($)
  if (!('cfg' in res)) return
  st.retry?.cancel()
  st.retry = null
  await startReporting($, res.cfg)
}

async function startReporting($: EngineInterface, cfg: Config): Promise<void> {
  st.cfg = cfg
  $.ui.log(`mc-lane: reporting to Mission Control, settings read from ${cfg.source}`)

  // Events a previous session on this machine could not send before it ended.
  for (const key of await $.store.keys()) {
    if (!key.startsWith(PENDING)) continue
    const saved = await $.store.get(key)
    if (Array.isArray(saved)) await update($, queue, append(saved as LaneEvent[]))
    await $.store.delete(key)
  }

  // A reload re-runs session.start in the same session: record its start once.
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
}

export const register: Register = on => {
  // Before the first prompt, and again after every reload of this module.
  on('session.start', async ($, e, next) => {
    st.sessionId = await $.session.id()
    st.cfg = null
    const res = await resolveLane($)
    if ('cfg' in res) {
      await startReporting($, res.cfg)
    } else {
      $.ui.log(`not reporting to Mission Control: ${res.why}; looking again every ${RETRY_MS / 1000} s`)
      if (!st.retry) st.retry = $.clock.every(RETRY_MS, () => retryLane($))
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
