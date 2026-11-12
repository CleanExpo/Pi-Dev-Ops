// mission-control — the fleet at a glance, inside Claude Code. Read-only.
//
// /mc opens a pane: one row per machine (host, status, heartbeat age; stale,
// runner-down and offline in red), the open-claim count, the last five ships,
// and a banner whenever the read is degraded or unknown. It refreshes on open
// and every 30 s while open. The tool `fleet_status` (Claude sees it as
// mcp__mission-control__fleet_status) returns the same summary as JSON text.
//
// Data: GET {MC_LANE_URL}/api/mesh/fleet with X-Pi-CEO-Secret (app/server/
// routes/mesh.py fleet(); app/server/mesh_fleet_auth.py accepts the machine
// secret). Nothing is written anywhere.
//
// Configuration, the same as mc-lane (lane_config.ts says why and how):
//   MC_LANE_URL     Pi-CEO backend base URL
//   MC_LANE_SECRET  the X-Pi-CEO-Secret the fleet already uses
// Read from this process's environment, else from launchd (`/bin/launchctl getenv`),
// as a pair from one place. Checked again on every tool call and /mc while missing,
// so an app that started before the launch agent finds them without a restart.
// With neither place holding both, /mc and the tool say "not configured", naming
// what each place holds by setting name only, and nothing is fetched.
//
// Functions that take `$` are top-level declarations: the engine scans the
// module before loading it and refuses `$` handed to anything else.

import type { EngineInterface, Register } from 'claude-code'
import { formatAge, NO_HOLD_REASON, summarize, unknown, type FleetRead, type MachineRow, type Summary } from './fleet'
import {
  clean,
  fromLaunchctl,
  launchctlArgv,
  LAUNCHCTL_TIMEOUT_MS,
  notConfiguredDetail,
  pickLaneConfig,
  type LaneConfig,
  type LaneVars,
  type LaunchdRead,
} from './lane_config'

const PANE = 'mission-control'
const TOOL = 'mcp__mission-control__fleet_status'
const EVERY_MS = 30_000

type Timer = { cancel(): void }
type Resolved = { cfg: LaneConfig } | { why: string }

// Module state. A reload starts it over (and the engine stops the old timers).
const st = {
  cfg: null as LaneConfig | null,
  summary: null as Summary | null,
  timer: null as Timer | null,
  inFlight: false,
}

async function launchdValue($: EngineInterface, name: string): Promise<string | undefined> {
  return fromLaunchctl(await $.process.run(launchctlArgv(name), { timeoutMs: LAUNCHCTL_TIMEOUT_MS }))
}

async function readLaunchd($: EngineInterface): Promise<LaunchdRead> {
  try {
    return { vars: { url: await launchdValue($, 'MC_LANE_URL'), secret: await launchdValue($, 'MC_LANE_SECRET') } }
  } catch (err) {
    return { error: err instanceof Error ? err.name : 'error' }
  }
}

// Environment first; launchd only when the environment lacks the pair. A miss is never kept,
// so the next call looks again. A hit is kept for the life of this load.
async function resolveConfig($: EngineInterface): Promise<Resolved> {
  if (st.cfg) return { cfg: st.cfg }
  const env: LaneVars = { url: clean(await $.env.get('MC_LANE_URL')), secret: clean(await $.env.get('MC_LANE_SECRET')) }
  let launchd: LaunchdRead | null = null
  let cfg = pickLaneConfig(env, null)
  if (!cfg) {
    launchd = await readLaunchd($)
    cfg = 'vars' in launchd ? pickLaneConfig(env, launchd.vars) : null
  }
  if (!cfg) return { why: `mission-control ${notConfiguredDetail(env, launchd)}` }
  st.cfg = cfg
  $.ui.log(`mission-control: settings read from ${cfg.source}`)
  return { cfg }
}

/** An error text with the secret cut out, in case a transport quotes the request it failed on. */
const scrub = (text: string, secret: string) => text.split(secret).join('[redacted]')

async function readFleet($: EngineInterface, cfg: LaneConfig): Promise<FleetRead> {
  try {
    const r = await $.http.fetch(`${cfg.url}/api/mesh/fleet`, {
      method: 'GET',
      headers: { 'X-Pi-CEO-Secret': cfg.secret, Accept: 'application/json' },
    })
    return { status: r.status, text: r.text }
  } catch (err) {
    return { error: scrub(err instanceof Error ? err.message : String(err), cfg.secret) }
  }
}

async function fetchSummary($: EngineInterface): Promise<Summary> {
  const res = await resolveConfig($)
  if ('why' in res) return unknown(res.why)
  const sum = summarize(await readFleet($, res.cfg), await $.clock.now())
  return { ...sum, configSource: res.cfg.source }
}

function machineLine(m: MachineRow): string {
  const note = m.placeholder ? '  cloud claim placeholder' : m.stale ? '  stale' : ''
  if (!m.held) return `${m.host}  ${m.status}  ${formatAge(m.ageS)}${note}`
  return `${m.host}  held: ${m.status}  ${formatAge(m.ageS)}  ${m.holdReason ?? NO_HOLD_REASON}${note}`
}

// One read at a time for the pane; a tick that lands while one is out is skipped.
async function refresh($: EngineInterface): Promise<void> {
  if (st.inFlight) return
  st.inFlight = true
  try {
    st.summary = await fetchSummary($)
  } finally {
    st.inFlight = false
  }
  $.ui.invalidate('ui.render')
}

function stopTimer(): void {
  st.timer?.cancel()
  st.timer = null
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    st.cfg = null // resolved on first use (resolveConfig), not here, so session start never waits on launchctl
    // Registered either way, so an unconfigured machine is told why rather than shown nothing.
    try {
      await $.tool.register({
        name: 'fleet_status',
        description:
          'Read-only Mission Control fleet summary: each machine (host, status, heartbeat age, stale), ' +
          'open claim count, last 5 ships, and whether the read is degraded or unknown (with the reason).',
        inputSchema: { type: 'object', properties: {} },
      })
      await $.command.register({ name: 'mc', description: 'Open the Mission Control fleet pane' })
    } catch (err) {
      $.ui.log(`mission-control: ${err instanceof Error ? err.message : String(err)}`)
    }
    return next(e)
  })

  on('command.run', { command: 'mc' }, async $ => {
    const res = await resolveConfig($)
    if ('why' in res) return { text: res.why }
    await $.ui.open({ id: PANE, title: 'Mission Control', closeOnEscape: true })
    stopTimer()
    st.timer = $.clock.every(EVERY_MS, () => refresh($))
    await refresh($)
    return {}
  })

  on('ui.close', async ($, e, next) => {
    if (e.id === PANE) stopTimer()
    return next(e)
  })

  on('tool.call', { tool: TOOL }, async $ => {
    const sum = await fetchSummary($)
    return { result: JSON.stringify(sum) }
  })

  on('ui.render', { component: 'Pane' }, async ($, e, next) => {
    if (e.requestId !== PANE) return next(e)
    const { Box, Text, Button } = $.ui.resolve(e)
    const sum = st.summary
    const rows: unknown[] = []

    if (!sum) {
      rows.push(Text({ dimColor: true, children: ['Reading the fleet…'] }))
    } else {
      if (sum.state !== 'ok') {
        const label = sum.state === 'unknown' ? 'FLEET UNKNOWN' : 'FLEET DEGRADED'
        rows.push(Text({ color: 'red', bold: true, wrap: 'wrap', children: [`${label}: ${sum.reason ?? ''}`] }))
      }
      if (sum.state !== 'unknown') {
        rows.push(Text({ bold: true, children: [`Machines (${sum.machines.length})`] }))
        if (sum.machines.length === 0) rows.push(Text({ dimColor: true, children: ['no machines have joined'] }))
        for (const m of sum.machines) {
          const line = machineLine(m)
          rows.push(Box({ key: `machine-${m.host}`, children: [Text(m.alert ? { color: 'red', children: [line] } : { children: [line] })] }))
        }
        rows.push(Text({ children: [`Open claims: ${sum.openClaims ?? 'unknown'}`] }))
        rows.push(Text({ bold: true, children: ['Recent ships'] }))
        if (sum.recentShips.length === 0) rows.push(Text({ dimColor: true, children: ['none'] }))
        for (const s of sum.recentShips) {
          rows.push(Text({ wrap: 'truncate-end', children: [`${formatAge(s.ageS)}  ${s.machine}  ${s.repo}  ${s.subject}`] }))
        }
      }
    }
    rows.push(Button({ key: 'refresh', label: 'Refresh', hotkey: 'r', plain: true, onPress: () => refresh($) }))
    return Box({ flexDirection: 'column', children: rows })
  })
}
