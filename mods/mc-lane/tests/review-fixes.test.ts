import { describe, expect, mock, test } from 'claude-code/testing'
import { scrubSecret } from '../hooks/lane_config'

// Why this file exists: the independent review of 0f957df9 found two defects in mc-lane.
// 1. With the URL and secret in the environment but no host there, launchd was never asked
//    for MC_LANE_HOST, so this machine's events were sent as host "unknown".
// 2. A transport error that quoted the request header reached the status line unscrubbed,
//    so the secret could show in Claude Code's status bar.

const SENTINEL = 'SENTINEL-not-a-secret-7f3a' // never a real value
// A cut-down secret is still a leak: any line holding the first 8 characters fails.
const leaks = (l: string) => l.includes(SENTINEL.slice(0, 8))
const ENV_PAIR = { MC_LANE_URL: 'https://mc.example/', MC_LANE_SECRET: 's3cret' }

type Post = { url: string; secret: string; host: string }

function harness(
  on: any,
  opts: { env: Record<string, string>; launchd?: Record<string, string>; fetchThrows?: string; okText?: string },
) {
  const posts: Post[] = []
  const lines: string[] = [] // every log and status line the mod writes
  const clock = mock.clock(on, { now: 1_700_000_000_000 })
  mock.env(on, opts.env)
  mock.store(on, {})
  on('session.id', () => ({ value: 'sess-r' }))
  on('session.repo', () => ({ value: null }))
  on('session.model', () => ({ value: 'claude-opus-5-5' }))
  on('session.start', () => ({ cwd: '/w' }))
  on('ui.log', ($: unknown, e: { text: string }) => {
    lines.push(e.text)
    return { value: undefined }
  })
  on('ui.status', ($: unknown, e: { text?: string }) => {
    if (e?.text) lines.push(e.text)
    return { value: undefined }
  })
  on('process.run', ($: unknown, e: { argv: string[] }) => {
    const v = (opts.launchd ?? {})[e.argv[2]]
    return { value: { exitCode: 0, stdout: v === undefined ? '' : `${v}\n`, stderr: '' } }
  })
  on('tool.call', () => ({ result: 'ok' }))
  on('http.fetch', ($: unknown, e: { url: string; init: { headers: Record<string, string>; body: string } }) => {
    const body = JSON.parse(e.init.body) as { host: string }
    posts.push({ url: e.url, secret: e.init.headers['X-Pi-CEO-Secret'], host: body.host })
    if (opts.fetchThrows) return { deny: opts.fetchThrows }
    return { value: { status: 200, ok: true, headers: {}, text: opts.okText ?? JSON.stringify({ acked: {} }) } }
  })
  return { posts, lines, clock }
}

const start = ($: any) => $.session.start({ surface: 'terminal', isInteractive: true, cwd: '/w' })

describe('host comes from launchd when only the environment holds the pair', () => {
  test('environment URL and secret, launchd host: events carry the launchd host', async ($, on) => {
    const h = harness(on, { env: ENV_PAIR, launchd: { MC_LANE_HOST: 'Phills-Mac-mini' } })
    await start($)
    await h.clock.advance(5_000)
    expect(h.posts.length).toBe(1) // positive control: it reported
    expect(h.posts[0].host).toBe('Phills-Mac-mini')
  })

  test('the pair still comes from one place: launchd URL and secret never replace the environment pair', async ($, on) => {
    const h = harness(on, {
      env: ENV_PAIR,
      launchd: { MC_LANE_URL: 'https://elsewhere.example', MC_LANE_SECRET: SENTINEL, MC_LANE_HOST: 'Phills-Mac-mini' },
    })
    await start($)
    await h.clock.advance(5_000)
    expect(h.posts[0].url).toBe('https://mc.example/api/mesh/lane-events')
    expect(h.posts[0].secret).toBe('s3cret')
    expect(h.posts[0].host).toBe('Phills-Mac-mini')
  })
})

describe('a transport error never carries the secret to the screen', () => {
  test('an error quoting the header: status says unreachable, the secret appears nowhere', async ($, on) => {
    const h = harness(on, { env: {}, launchd: { MC_LANE_URL: 'https://mc.example', MC_LANE_SECRET: SENTINEL }, fetchThrows: `connect failed; header X-Pi-CEO-Secret: ${SENTINEL}` })
    await start($)
    await h.clock.advance(5_000)
    expect(h.posts.length).toBe(1) // positive control: the request was made with the secret
    expect(h.posts[0].secret).toBe(SENTINEL)
    expect(h.lines.some(l => l.startsWith('Mission Control unreachable'))).toBe(true)
    expect(h.lines.some(leaks)).toBe(false)
  })

  test('a reply that is not JSON and echoes the secret: the parse error never shows it', async ($, on) => {
    const h = harness(on, { env: {}, launchd: { MC_LANE_URL: 'https://mc.example', MC_LANE_SECRET: SENTINEL }, okText: SENTINEL })
    await start($)
    await h.clock.advance(5_000)
    expect(h.posts.length).toBe(1)
    expect(h.lines.some(l => l.startsWith('Mission Control unreachable (reply is not JSON)'))).toBe(true) // reported, as a fixed text
    expect(h.lines.some(leaks)).toBe(false)
  })

  test('scrubSecret cuts every copy, and a cut before truncation leaves no prefix', () => {
    expect(scrubSecret(`a ${SENTINEL} b ${SENTINEL}`, SENTINEL)).toBe('a [redacted] b [redacted]')
    expect(scrubSecret('no secret here', SENTINEL)).toBe('no secret here')
    expect(scrubSecret('text', '')).toBe('text')
    const long = `${'x'.repeat(70)}${SENTINEL}`
    expect(scrubSecret(long, SENTINEL).slice(0, 80).includes(SENTINEL.slice(0, 10))).toBe(false)
  })
})
