import { describe, expect, mock, test } from 'claude-code/testing'
import { summarize } from '../hooks/fleet'

// Why this file exists: a machine the runner holds (Claude quota exhausted, blocked, stuck,
// outdated, ...) heartbeats on time, so before 12/11/2026 it showed as healthy. Only `online`
// and `working` are healthy now (HEALTHY_STATUSES, shared with the Live page and pinned by
// tests/test_fleet_status_vocabulary.py); a held one is red and says why.

const NOW = Date.parse('2026-11-12T03:00:00Z')
const ago = (s: number) => new Date(NOW - s * 1000).toISOString()
const NO_REASON = "reason not reported by this machine's heartbeat"
const runner = (extra: Record<string, unknown>) => [{ runtime: 'mesh-runner', present: true, state: 'quota', state_age_s: 10, ...extra }]
const HELD = [
  { host: 'q', status: 'quota', last_seen: ago(5), is_stale: false, agent_runtimes: runner({ hold_reason: 'Claude quota exhausted until 14:00' }) },
  // The Mini's heartbeat (pdo-runtime, 5 Nov) sends the status word with no mesh-runner entry.
  { host: 'q2', status: 'quota', last_seen: ago(5), is_stale: false },
  { host: 'u', status: 'updating', last_seen: ago(5), is_stale: false },
  { host: 'n', last_seen: ago(5), is_stale: false },
  { host: 'w', status: 'working', last_seen: ago(5), is_stale: false },
  { host: 'gone', status: 'blocked', last_seen: ago(5), is_stale: false, agent_runtimes: runner({ present: false, hold_reason: 'old' }) },
  { host: 'long', status: 'stuck', last_seen: ago(5), is_stale: false, agent_runtimes: runner({ hold_reason: 'x'.repeat(300) }) },
]
const SNAPSHOT = { machines: HELD, agents: [], ships: [], claims: [], degraded: false, errors: [] }
const ok = { status: 200, text: JSON.stringify(SNAPSHOT) }

describe('summarize: held and unhealthy statuses', () => {
  test('only online and working are healthy: held, updating and missing statuses all alert', () => {
    const s = summarize(ok, NOW)
    expect(s.machines.map(m => [m.host, m.status, m.alert, m.held])).toEqual([
      ['q', 'quota', true, true],
      ['q2', 'quota', true, true],
      ['u', 'updating', true, false],
      ['n', 'unknown', true, false],
      ['w', 'working', false, false],
      ['gone', 'blocked', true, true],
      ['long', 'stuck', true, true],
    ])
  })

  test('the hold reason comes only from a present mesh-runner entry, trimmed to 120 characters', () => {
    const by = Object.fromEntries(summarize(ok, NOW).machines.map(m => [m.host, m]))
    expect(by.q.holdReason).toBe('Claude quota exhausted until 14:00')
    expect(by.q2.holdReason).toBe(null)
    expect(by.gone.holdReason).toBe(null)
    expect(by.long.holdReason?.length).toBe(120)
    expect(by.w.holdReason).toBe(null)
  })
})

describe('/mc pane', () => {
  test('held machines are red and say why, or say the reason was not reported', async ($, on) => {
    mock.clock(on, { now: NOW })
    mock.env(on, { MC_LANE_URL: 'https://mc.example', MC_LANE_SECRET: 'SENTINEL-not-a-secret-7f3a' })
    on('session.start', () => ({ cwd: '/w' }))
    on('tool.register', () => ({ value: undefined }))
    on('command.register', () => ({ value: undefined }))
    on('ui.log', () => ({ value: undefined }))
    on('ui.open', () => ({ value: { isPlaced: true } }))
    on('ui.render', () => ({ type: 'Text', props: {}, children: ['drawn by Claude Code'] }))
    on('http.fetch', () => ({ value: { status: 200, ok: true, headers: {}, text: ok.text } }))
    await $.session.start({ surface: 'terminal', isInteractive: true, cwd: '/w' })
    await $.command.run({ command: 'mc', args: '' })
    const ui = await $.ui.mount({
      plugin: 'mission-control', component: 'Pane', requestId: 'mission-control', surface: 'terminal',
      viewport: { columns: 120, rows: 40 },
      props: { title: 'Mission Control', isFocused: false, bodyColumns: 80, placement: 'inline', scroll: { offset: 0, bodyRows: 20 }, view: {} },
    })
    const q = await ui.find({ type: 'Text', text: 'q  held: quota  5s  Claude quota exhausted until 14:00' })
    expect(q?.props.color).toBe('red')
    expect((await ui.find({ type: 'Text', text: `q2  held: quota  5s  ${NO_REASON}` }))?.props.color).toBe('red')
    expect((await ui.find({ type: 'Text', text: 'u  updating  5s' }))?.props.color).toBe('red')
    expect((await ui.find({ type: 'Text', text: 'w  working  5s' }))?.props.color).toBeUndefined()
    await ui.unmount()
  })
})
