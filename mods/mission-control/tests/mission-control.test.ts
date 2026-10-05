import { describe, expect, mock, test } from 'claude-code/testing'
import { formatAge, summarize } from '../hooks/fleet'

const NOW = Date.parse('2026-10-06T00:00:00Z')
const ago = (s: number) => new Date(NOW - s * 1000).toISOString()
const ENV = { MC_LANE_URL: 'https://mc.example/', MC_LANE_SECRET: 's3cret' }
const TOOL = 'mcp__mission-control__fleet_status'

const SNAPSHOT = {
  machines: [
    { host: 'Phills-Mac-mini', status: 'working', last_seen: ago(8), is_stale: false, active_agents: 2 },
    { host: 'unite-mbp', status: 'runner-down', last_seen: ago(20), is_stale: false, active_agents: 0 },
    { host: 'old-box', status: 'online', last_seen: ago(900), is_stale: true, active_agents: 0 },
  ],
  agents: [],
  ships: Array.from({ length: 7 }, (_, i) => ({
    machine: 'Phills-Mac-mini', repo: 'CleanExpo/Pi-Dev-Ops', sha: 'abcdef1234', subject: `ship ${i}`, shipped_at: ago(60 * (i + 1)),
  })),
  claims: [{ linear_id: 'RA-1', state: 'working' }, { linear_id: 'RA-2', state: 'claimed' }],
  degraded: false,
  errors: [],
}

const ok = (body: unknown) => ({ status: 200, text: JSON.stringify(body) })

const PANE = {
  plugin: 'mission-control',
  component: 'Pane',
  requestId: 'mission-control',
  viewport: { columns: 120, rows: 40 },
  props: {
    title: 'Mission Control',
    isFocused: false,
    bodyColumns: 80,
    placement: 'inline',
    scroll: { offset: 0, bodyRows: 20 },
    view: {},
  },
} as const

type Fetch = { url: string; headers: Record<string, string> }

/** Stubs what session.start, /mc and the tool call. */
function harness(on: any, opts: { env?: Record<string, string>; answer?: { status: number; text: string } } = {}) {
  const fetches: Fetch[] = []
  const opened: unknown[] = []
  const logs: string[] = []
  const clock = mock.clock(on, { now: NOW })
  mock.env(on, opts.env ?? ENV)
  on('session.start', () => ({ cwd: '/w' }))
  on('tool.register', () => ({ value: undefined }))
  on('command.register', () => ({ value: undefined }))
  on('ui.log', ($: unknown, e: { text: string }) => {
    logs.push(e.text)
    return { value: undefined }
  })
  on('ui.open', ($: unknown, e: unknown) => {
    opened.push(e)
    return { value: { isPlaced: true } }
  })
  on('ui.render', () => ({ type: 'Text', props: {}, children: ['drawn by Claude Code'] }))
  on('http.fetch', ($: unknown, e: { url: string; init: { headers: Record<string, string> } }) => {
    fetches.push({ url: e.url, headers: e.init.headers })
    const a = opts.answer ?? ok(SNAPSHOT)
    return { value: { status: a.status, ok: a.status < 300, headers: {}, text: a.text } }
  })
  return { fetches, opened, logs, clock }
}

const start = ($: any) => $.session.start({ surface: 'terminal', isInteractive: true, cwd: '/w' })

describe('summarize', () => {
  test('a healthy snapshot: machines, runner-down and stale flagged, claims counted, five ships', () => {
    const s = summarize(ok(SNAPSHOT), NOW)
    expect(s.state).toBe('ok')
    expect(s.degraded).toBe(false)
    expect(s.machines.map(m => [m.host, m.status, m.ageS, m.stale, m.alert])).toEqual([
      ['Phills-Mac-mini', 'working', 8, false, false],
      ['unite-mbp', 'runner-down', 20, false, true],
      ['old-box', 'online', 900, true, true],
    ])
    expect(s.openClaims).toBe(2)
    expect(s.recentShips.length).toBe(5)
    expect(s.recentShips[0]).toEqual({ machine: 'Phills-Mac-mini', repo: 'CleanExpo/Pi-Dev-Ops', subject: 'ship 0', sha: 'abcdef1', ageS: 60 })
  })

  test('a heartbeat older than 60 s is stale even when the view says otherwise', () => {
    const s = summarize(ok({ ...SNAPSHOT, machines: [{ host: 'h', status: 'online', last_seen: ago(61), is_stale: false }] }), NOW)
    expect(s.machines[0].stale).toBe(true)
  })

  test('401 is unknown with the reason, never an empty healthy fleet', () => {
    const s = summarize({ status: 401, text: '{"detail":"Invalid or missing X-Pi-CEO-Secret"}' }, NOW)
    expect(s.state).toBe('unknown')
    expect(s.degraded).toBe(true)
    expect(s.reason).toBe('HTTP 401: secret refused')
    expect(s.machines).toEqual([])
    expect(s.openClaims).toBe(null)
  })

  test('an HTML error page is unknown', () => {
    const s = summarize({ status: 200, text: '<html><body>502 Bad Gateway</body></html>' }, NOW)
    expect(s.state).toBe('unknown')
    expect(s.reason).toBe('response is not JSON')
  })

  test('JSON that is not the snapshot is unknown', () => {
    expect(summarize(ok({ machines: {} }), NOW).state).toBe('unknown')
    expect(summarize(ok([]), NOW).state).toBe('unknown')
    expect(summarize({ status: 503, text: '{}' }, NOW).reason).toBe('HTTP 503')
    expect(summarize({ error: 'getaddrinfo ENOTFOUND' }, NOW).reason).toBe('request failed: getaddrinfo ENOTFOUND')
  })

  test('a degraded snapshot is never healthy, and a failed claims source is not zero claims', () => {
    const s = summarize(ok({
      machines: [], agents: [], ships: [], claims: [], degraded: true,
      errors: [{ source: 'claims', status: 500, reason: 'http-error' }],
    }), NOW)
    expect(s.state).toBe('degraded')
    expect(s.degraded).toBe(true)
    expect(s.reason).toBe('server degraded: claims http-error 500')
    expect(s.openClaims).toBe(null)
  })

  test('formatAge', () => {
    expect(formatAge(null)).toBe('?')
    expect(formatAge(12)).toBe('12s')
    expect(formatAge(600)).toBe('10m')
    expect(formatAge(3 * 3600)).toBe('3h')
    expect(formatAge(3 * 86_400)).toBe('3d')
  })
})

describe('fleet_status tool', () => {
  test('returns the summary as JSON, read with the secret header', async ($, on) => {
    const h = harness(on)
    await start($)
    const out = await $.tool.call({ tool: TOOL })
    expect(h.fetches.length).toBe(1)
    expect(h.fetches[0].url).toBe('https://mc.example/api/mesh/fleet')
    expect(h.fetches[0].headers['X-Pi-CEO-Secret']).toBe('s3cret')
    const s = JSON.parse(out.result as string)
    expect(s.state).toBe('ok')
    expect(s.machines.length).toBe(3)
    expect(s.openClaims).toBe(2)
  })

  test('unconfigured: still returns a result, says why, fetches nothing', async ($, on) => {
    const h = harness(on, { env: {} })
    await start($)
    const out = await $.tool.call({ tool: TOOL })
    expect(h.fetches.length).toBe(0)
    const s = JSON.parse(out.result as string)
    expect(s.state).toBe('unknown')
    expect(s.reason).toBe('mission-control not configured: MC_LANE_URL / MC_LANE_SECRET unset')
  })

  test('a 401 comes back as an unknown result, not an error', async ($, on) => {
    on('tool.call', () => ({ result: 'not ours' }))
    harness(on, { answer: { status: 401, text: 'nope' } })
    await start($)
    const out = await $.tool.call({ tool: TOOL })
    expect(JSON.parse(out.result as string).state).toBe('unknown')
  })
})

describe('/mc', () => {
  test('opens the pane and draws one row per machine, runner-down in red', async ($, on) => {
    const h = harness(on)
    await start($)
    const answer = await $.command.run({ command: 'mc', args: '' })
    expect(answer.text).toBeUndefined()
    expect(h.opened).toEqual([{ id: 'mission-control', title: 'Mission Control', closeOnEscape: true }])
    expect(h.fetches.length).toBe(1)

    const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
    const down = await ui.find({ type: 'Text', text: 'unite-mbp  runner-down  20s' })
    expect(down).toBeDefined()
    expect(down?.props.color).toBe('red')
    const fresh = await ui.find({ type: 'Text', text: 'Phills-Mac-mini  working  8s' })
    expect(fresh?.props.color).toBeUndefined()
    expect(await ui.find({ type: 'Text', text: 'old-box  online  15m  stale' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: 'Open claims: 2' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /ship 4$/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /ship 5$/ })).toBeUndefined()
    expect(await ui.find({ type: 'Text', text: /^FLEET / })).toBeUndefined()
    await ui.unmount()
  })

  test('refreshes every 30 s while open', async ($, on) => {
    const h = harness(on)
    await start($)
    await $.command.run({ command: 'mc', args: '' })
    await h.clock.advance(30_000)
    await h.clock.advance(30_000)
    expect(h.fetches.length).toBe(3)
  })

  test('a 401 draws the unknown banner and no machine rows', async ($, on) => {
    harness(on, { answer: { status: 401, text: 'nope' } })
    await start($)
    await $.command.run({ command: 'mc', args: '' })
    const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
    const banner = await ui.find({ type: 'Text', text: 'FLEET UNKNOWN: HTTP 401: secret refused' })
    expect(banner?.props.color).toBe('red')
    expect(await ui.find({ type: 'Text', text: /^Machines/ })).toBeUndefined()
    await ui.unmount()
  })

  test('unconfigured: says so and opens nothing', async ($, on) => {
    const h = harness(on, { env: {} })
    await start($)
    const answer = await $.command.run({ command: 'mc', args: '' })
    expect(answer.text).toBe('mission-control not configured: MC_LANE_URL / MC_LANE_SECRET unset')
    expect(h.opened.length).toBe(0)
    expect(h.fetches.length).toBe(0)
  })

  test('other panes are left alone', async ($, on) => {
    harness(on)
    const ui = await $.ui.mount({ ...PANE, requestId: 'someone-else', surface: 'terminal' })
    expect(await ui.find({ type: 'Text', text: 'drawn by Claude Code' })).toBeDefined()
    await ui.unmount()
  })
})
