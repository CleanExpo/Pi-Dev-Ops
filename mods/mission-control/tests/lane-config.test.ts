import { describe, expect, mock, test } from 'claude-code/testing'
import { fromLaunchctl, pickLaneConfig } from '../hooks/lane_config'

// Why this file exists: after a reboot the desktop app can start before the launch agent
// that copies MC_LANE_* into launchd (observed 12/11/2026: app 11:59:45, agent 11:59:46).
// launchctl setenv never reaches a running process, so the app's own environment lacks
// them for its whole life while launchd holds them. The mod must read launchd itself.

const SENTINEL = 'SENTINEL-not-a-secret-7f3a' // never a real value (CLAUDE.md rule 4)
const URL_ = 'https://mc.example'
const TOOL = 'mcp__mission-control__fleet_status'
const NOW = Date.parse('2026-11-12T03:00:00Z')
const SNAPSHOT = {
  machines: [{ host: 'Phills-Mac-mini', status: 'working', last_seen: new Date(NOW - 5000).toISOString(), is_stale: false }],
  agents: [], ships: [], claims: [], degraded: false, errors: [],
}

type Run = { argv: string[]; timeoutMs?: number }
type Launchd = Record<string, string> | 'refuse'

function harness(on: any, opts: { env?: Record<string, string>; launchd?: () => Launchd; fetchThrows?: string } = {}) {
  const runs: Run[] = []
  const fetches: { url: string; secret: string }[] = []
  const logs: string[] = []
  mock.clock(on, { now: NOW })
  mock.env(on, opts.env ?? {})
  on('session.start', () => ({ cwd: '/w' }))
  on('tool.register', () => ({ value: undefined }))
  on('command.register', () => ({ value: undefined }))
  on('ui.log', ($: unknown, e: { text: string }) => {
    logs.push(e.text)
    return { value: undefined }
  })
  on('process.run', ($: unknown, e: { argv: string[]; init?: { timeoutMs?: number } }) => {
    runs.push({ argv: e.argv, timeoutMs: e.init?.timeoutMs })
    const l = (opts.launchd ?? (() => ({})))()
    if (l === 'refuse') return { deny: 'policy: mods may not call process.run' }
    const name = e.argv[2]
    // The real launchctl: an unset name prints nothing and still exits 0 (checked on the Mini).
    return { value: { exitCode: 0, stdout: l[name] !== undefined ? `${l[name]}\n` : '', stderr: '' } }
  })
  on('http.fetch', ($: unknown, e: { url: string; init: { headers: Record<string, string> } }) => {
    fetches.push({ url: e.url, secret: e.init.headers['X-Pi-CEO-Secret'] })
    if (opts.fetchThrows) return { deny: opts.fetchThrows }
    return { value: { status: 200, ok: true, headers: {}, text: JSON.stringify(SNAPSHOT) } }
  })
  return { runs, fetches, logs }
}

const start = ($: any) => $.session.start({ surface: 'terminal', isInteractive: true, cwd: '/w' })
const BOTH = { MC_LANE_URL: `${URL_}/`, MC_LANE_SECRET: SENTINEL }

describe('fromLaunchctl', () => {
  test('a value is one line; unset prints nothing and exits 0, which is absent, not empty', () => {
    expect(fromLaunchctl({ exitCode: 0, stdout: 'https://x\n' })).toBe('https://x')
    expect(fromLaunchctl({ exitCode: 0, stdout: '' })).toBe(undefined)
    expect(fromLaunchctl({ exitCode: 0, stdout: '\n' })).toBe(undefined)
    expect(fromLaunchctl({ exitCode: 0, stdout: '   \n' })).toBe(undefined)
    expect(fromLaunchctl({ exitCode: 1, stdout: 'https://x\n' })).toBe(undefined)
    expect(fromLaunchctl({ exitCode: 0, stdout: 'a\nb\n' })).toBe(undefined)
    expect(fromLaunchctl(null)).toBe(undefined)
  })
})

describe('pickLaneConfig', () => {
  test('URL and secret come as a pair from one source, environment first', () => {
    const env = pickLaneConfig({ url: 'https://e/', secret: 'es' }, { url: 'https://l', secret: 'ls' })
    expect(env).toEqual({ url: 'https://e', secret: 'es', host: 'unknown', source: 'env' })
    // Environment holds only half: launchd's pair is used whole, never a mix of the two.
    const mixed = pickLaneConfig({ url: 'https://e' }, { url: 'https://l', secret: 'ls', host: 'mini' })
    expect(mixed).toEqual({ url: 'https://l', secret: 'ls', host: 'mini', source: 'launchd' })
    expect(pickLaneConfig({ url: 'https://e' }, { secret: 'ls' })).toBe(null)
    expect(pickLaneConfig({}, null)).toBe(null)
    expect(pickLaneConfig({ url: ' ', secret: ' ' }, null)).toBe(null)
  })
})

describe('fleet_status reads launchd when the environment lacks the settings', () => {
  test('configured from launchd: real read, sentinel sent as the header and never shown', async ($, on) => {
    const h = harness(on, { launchd: () => BOTH })
    await start($)
    const out = await $.tool.call({ tool: TOOL })
    // Positive controls first: the configured path really ran.
    expect(h.fetches.length).toBe(1)
    expect(h.fetches[0].url).toBe(`${URL_}/api/mesh/fleet`)
    expect(h.fetches[0].secret).toBe(SENTINEL)
    const s = JSON.parse(out.result as string)
    expect(s.state).toBe('ok')
    expect(s.configSource).toBe('launchd')
    expect(h.logs.some(l => l.includes('launchd'))).toBe(true)
    // Then the absence check, over output that exists.
    expect(String(out.result).includes(SENTINEL)).toBe(false)
    expect(h.logs.some(l => l.includes(SENTINEL))).toBe(false)
    // Absolute path, argument list, short timeout, and only the two names it needs.
    expect(h.runs.map(r => r.argv)).toEqual([
      ['/bin/launchctl', 'getenv', 'MC_LANE_URL'],
      ['/bin/launchctl', 'getenv', 'MC_LANE_SECRET'],
    ])
    expect(h.runs.every(r => r.timeoutMs === 3000)).toBe(true)
  })

  test('the environment wins when it holds both: launchd is not asked', async ($, on) => {
    const h = harness(on, { env: { MC_LANE_URL: URL_, MC_LANE_SECRET: 'env-sentinel' }, launchd: () => BOTH })
    await start($)
    const s = JSON.parse((await $.tool.call({ tool: TOOL })).result as string)
    expect(h.runs.length).toBe(0)
    expect(h.fetches[0].secret).toBe('env-sentinel')
    expect(s.configSource).toBe('env')
  })

  test('nothing in either place: unknown, says where it looked, fetches nothing', async ($, on) => {
    const h = harness(on, { launchd: () => ({}) })
    await start($)
    const s = JSON.parse((await $.tool.call({ tool: TOOL })).result as string)
    expect(h.runs.length).toBeGreaterThan(0)
    expect(h.fetches.length).toBe(0)
    expect(s.state).toBe('unknown')
    expect(s.reason).toContain('not configured')
    expect(s.reason).toContain('environment: URL unset, secret unset')
    expect(s.reason).toContain('launchd: URL unset, secret unset')
  })

  test('launchd unreadable (process.run refused): unknown and says so, never configured', async ($, on) => {
    const h = harness(on, { launchd: () => 'refuse' })
    await start($)
    const s = JSON.parse((await $.tool.call({ tool: TOOL })).result as string)
    expect(h.fetches.length).toBe(0)
    expect(s.state).toBe('unknown')
    expect(s.reason).toContain('launchd: unreadable')
  })

  test('launchd filled after the session started: the next call finds it without a restart', async ($, on) => {
    let filled = false
    const h = harness(on, { launchd: () => (filled ? BOTH : {}) })
    await start($)
    const before = JSON.parse((await $.tool.call({ tool: TOOL })).result as string)
    expect(before.state).toBe('unknown')
    filled = true
    const after = JSON.parse((await $.tool.call({ tool: TOOL })).result as string)
    expect(after.state).toBe('ok')
    expect(after.configSource).toBe('launchd')
    expect(h.fetches.length).toBe(1)
  })

  test('/mc also re-checks: unconfigured at first, then opens once launchd is filled', async ($, on) => {
    let filled = false
    const h = harness(on, { launchd: () => (filled ? BOTH : {}) })
    on('ui.open', () => ({ value: { isPlaced: true } }))
    await start($)
    const before = await $.command.run({ command: 'mc', args: '' })
    expect(before.text).toContain('not configured')
    filled = true
    const after = await $.command.run({ command: 'mc', args: '' })
    expect(after.text).toBeUndefined()
    expect(h.fetches.length).toBe(1)
  })

  test('a transport error that quotes the secret does not carry it into the result or the log', async ($, on) => {
    const h = harness(on, { launchd: () => BOTH, fetchThrows: `connect failed; header X-Pi-CEO-Secret: ${SENTINEL}` })
    await start($)
    const out = await $.tool.call({ tool: TOOL })
    expect(h.fetches.length).toBe(1)
    const s = JSON.parse(out.result as string)
    expect(s.state).toBe('unknown')
    expect(s.reason).toContain('request failed')
    expect(String(out.result).includes(SENTINEL)).toBe(false)
    expect(h.logs.some(l => l.includes(SENTINEL))).toBe(false)
  })
})
