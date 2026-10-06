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
// Configuration (environment, read once per load), the same as mc-lane:
//   MC_LANE_URL     Pi-CEO backend base URL
//   MC_LANE_SECRET  the X-Pi-CEO-Secret the fleet already uses
// With either unset, /mc and the tool say "not configured" and nothing is fetched.
//
// Functions that take `$` are top-level declarations: the engine scans the
// module before loading it and refuses `$` handed to anything else.

import type { EngineInterface, Register } from 'claude-code'
import { formatAge, summarize, unknown, type FleetRead, type Summary } from './fleet'

const PANE = 'mission-control'
const TOOL = 'mcp__mission-control__fleet_status'
const EVERY_MS = 30_000
const NOT_CONFIGURED = 'mission-control not configured: MC_LANE_URL / MC_LANE_SECRET unset'

type Config = { url: string; secret: string }
type Timer = { cancel(): void }

// Module state. A reload starts it over (and the engine stops the old timers).
const st = {
  cfg: null as Config | null,
  summary: null as Summary | null,
  timer: null as Timer | null,
  inFlight: false,
}

async function readFleet($: EngineInterface, cfg: Config): Promise<FleetRead> {
  try {
    const r = await $.http.fetch(`${cfg.url}/api/mesh/fleet`, {
      method: 'GET',
      headers: { 'X-Pi-CEO-Secret': cfg.secret, Accept: 'application/json' },
    })
    return { status: r.status, text: r.text }
  } catch (err) {
    return { error: err instanceof Error ? err.message : String(err) }
  }
}

async function fetchSummary($: EngineInterface): Promise<Summary> {
  if (!st.cfg) return unknown(NOT_CONFIGURED)
  const read = await readFleet($, st.cfg)
  return summarize(read, await $.clock.now())
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
    const url = (await $.env.get('MC_LANE_URL'))?.replace(/\/+$/, '')
    const secret = await $.env.get('MC_LANE_SECRET')
    st.cfg = url && secret ? { url, secret } : null
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
    if (!st.cfg) return { text: NOT_CONFIGURED }
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
          const line = `${m.host}  ${m.status}  ${formatAge(m.ageS)}${m.stale ? '  stale' : ''}`
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
