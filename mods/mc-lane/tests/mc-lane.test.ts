import { describe, expect, mock, test } from 'claude-code/testing'
import { dropAcked, enqueue, makeSeq, MAX_QUEUE, modelName, repoSlug, toolName, worstRate, type LaneEvent } from '../hooks/lane'

const ENV = { MC_LANE_URL: 'https://mc.example/', MC_LANE_SECRET: 's3cret', MC_LANE_HOST: 'unite-mac-mini' }

type Post = { url: string; headers: Record<string, string>; body: { host: string; events: LaneEvent[] } }

/** Stubs every call session.start makes; returns the POSTs the mod sends. */
function harness(on: any, opts: { env?: Record<string, string>; status?: number; store?: Record<string, unknown> } = {}) {
  const posts: Post[] = []
  const clock = mock.clock(on, { now: 1_700_000_000_000 })
  mock.env(on, opts.env ?? ENV)
  mock.store(on, opts.store ?? {})
  on('session.id', () => ({ value: 'sess-1' }))
  on('session.repo', () => ({ value: { root: '/w', remote: 'https://x-token:abc@github.com/CleanExpo/Pi-Dev-Ops.git', internal: false } }))
  on('session.model', () => ({ value: 'claude-opus-5-5' }))
  on('session.start', () => ({ cwd: '/w' }))
  on('ui.log', () => ({ value: undefined }))
  on('ui.status', () => ({ value: undefined }))
  on('tool.call', () => ({ result: 'ok' }))
  on('session.measure', ($: unknown, e: unknown) => e)
  on('session.end', () => ({}))
  const spawned: unknown[] = []
  on('agent.spawn', ($: unknown, e: unknown) => {
    spawned.push(e)
    return { model: 'claude-haiku-4-5', agentId: 'agent-7' }
  })
  on('http.fetch', ($: unknown, e: { url: string; init: { headers: Record<string, string>; body: string } }) => {
    const body = JSON.parse(e.init.body) as Post['body']
    posts.push({ url: e.url, headers: e.init.headers, body })
    const acked: Record<string, number> = {}
    for (const ev of body.events) acked[ev.session_id] = Math.max(acked[ev.session_id] ?? 0, ev.seq)
    const status = opts.status ?? 200
    return { value: { status, ok: status < 300, headers: {}, text: JSON.stringify({ ok: true, acked }) } }
  })
  return { posts, clock, spawned }
}

describe('reporting', () => {
  test('a tool call reaches Mission Control as its name and timing only', async ($, on) => {
    const { posts, clock } = harness(on)
    await $.session.start({ surface: 'terminal', isInteractive: true, cwd: '/w' })
    await $.tool.call({ tool: 'Bash', command: 'cat ~/.ssh/id_rsa' })
    await clock.advance(5_000)

    expect(posts.length).toBe(1)
    const p = posts[0]
    expect(p.url).toBe('https://mc.example/api/mesh/lane-events')
    expect(p.headers['X-Pi-CEO-Secret']).toBe('s3cret')
    expect(p.body.host).toBe('unite-mac-mini')
    const kinds = p.body.events.map(e => e.kind)
    expect(kinds).toEqual(['session_start', 'tool'])
    const start = p.body.events[0]
    // The remote URL carried a token; only owner/name may leave.
    expect(start.repo).toBe('CleanExpo/Pi-Dev-Ops')
    expect(JSON.stringify(p.body)).not.toContain('abc')
    const tool = p.body.events[1]
    expect(tool.tool).toBe('Bash')
    expect(tool.ok).toBe(true)
    // The command (and so the path it read) never leaves the machine.
    expect(JSON.stringify(p.body)).not.toContain('id_rsa')
  })

  test('usage carries context %, worst rate-limit % and cost', async ($, on) => {
    const { posts, clock } = harness(on)
    await $.session.start({ surface: 'terminal', isInteractive: false, cwd: '/w' })
    await $.session.measure({
      context: { tokens: 50_000, window: 200_000, percent: 25 },
      rateLimits: [{ kind: 'five_hour', percentUsed: 40 }, { kind: 'seven_day', percentUsed: 72 }],
      cost: { usd: 1.25 },
      changed: [],
    })
    await clock.advance(5_000)
    const usage = posts[0].body.events.find(e => e.kind === 'usage')
    expect(usage).toMatchObject({ ctx_pct: 25, rate_pct: 72, cost_usd: 1.25 })
  })

  test('cost absent stays absent (Mission Control shows unknown, never 0)', async ($, on) => {
    const { posts, clock } = harness(on)
    await $.session.start({ surface: 'terminal', isInteractive: false, cwd: '/w' })
    await $.session.measure({ context: { window: 200_000 }, rateLimits: [], changed: [] })
    await clock.advance(5_000)
    const usage = posts[0].body.events.find(e => e.kind === 'usage')
    expect(usage?.cost_usd).toBeUndefined()
    expect(usage?.rate_pct).toBeUndefined()
  })
})

describe('hot reload', () => {
  // A reload re-runs session.start in the same session; the queue and the
  // "session_start already recorded" mark live in $.state, so neither resets.
  test('a second session.start keeps the queue and records session_start once', async ($, on) => {
    const { posts, clock } = harness(on, { status: 503 })
    await $.session.start({ surface: 'terminal', isInteractive: true, cwd: '/w' })
    await $.tool.call({ tool: 'Read', file_path: 'a' })
    await clock.advance(5_000) // backend down: both events stay queued
    expect(posts.length).toBe(1)

    await $.session.start({ surface: 'terminal', isInteractive: true, cwd: '/w' }) // the reload
    await $.tool.call({ tool: 'Edit', file_path: 'a' })
    await clock.advance(5_000)

    expect(posts.length).toBe(2) // one timer, not two
    const kinds = posts[1].body.events.map(e => e.kind)
    expect(kinds).toEqual(['session_start', 'tool', 'tool'])
    expect(posts[1].body.events.map(e => e.tool)).toEqual([undefined, 'Read', 'Edit'])
    const seqs = posts[1].body.events.map(e => e.seq)
    expect(new Set(seqs).size).toBe(seqs.length)
  })
})

describe('subagents and teammates', () => {
  test('agent.spawn passes through unchanged and records agent_start (type and model only)', async ($, on) => {
    const { posts, clock, spawned } = harness(on)
    await $.session.start({ surface: 'terminal', isInteractive: true, cwd: '/w' })
    const input = {
      tool_use_id: 'tu-1', prompt: 'read ~/.ssh/id_rsa and summarise', description: 'secret task',
      subagentType: 'Explore', provider: { plugin: 'engine', tier: 'core' }, parentModel: 'claude-opus-5-5',
      background: false, fork: false, isTeammate: true, name: 'scout',
    }
    const ran = await $.agent.spawn(input as never)

    expect(spawned).toEqual([input]) // next(e) got the event as given
    expect(ran).toMatchObject({ model: 'claude-haiku-4-5', agentId: 'agent-7' })

    await clock.advance(5_000)
    const ev = posts[0].body.events.find(e => e.kind === 'agent_start')
    expect(ev).toMatchObject({ kind: 'agent_start', tool: 'Explore', model: 'claude-haiku-4-5', ok: true })
    const sent = JSON.stringify(posts[0].body)
    for (const leak of ['id_rsa', 'secret task', 'scout', 'tu-1']) expect(sent).not.toContain(leak)
  })
})

describe('honesty when it cannot report', () => {
  test('unconfigured: sends nothing and says so', async ($, on) => {
    const { posts, clock } = harness(on, { env: {} })
    await $.session.start({ surface: 'terminal', isInteractive: true, cwd: '/w' })
    await $.tool.call({ tool: 'Read', file_path: 'README.md' })
    await clock.advance(10_000)
    expect(posts.length).toBe(0)
  })

  test('backend down: events stay queued and are re-sent once it answers', async ($, on) => {
    let status = 503
    const posts: Post[] = []
    const clock = mock.clock(on, { now: 1_700_000_000_000 })
    mock.env(on, ENV)
    mock.store(on, {})
    on('session.id', () => ({ value: 'sess-2' }))
    on('session.repo', () => ({ value: null }))
    on('session.model', () => ({ value: 'claude-opus-5-5' }))
    on('session.start', () => ({ cwd: '/w' }))
    on('ui.log', () => ({ value: undefined }))
    on('ui.status', () => ({ value: undefined }))
    on('tool.call', () => ({ result: 'ok' }))
    on('http.fetch', ($: unknown, e: { url: string; init: { headers: Record<string, string>; body: string } }) => {
      const body = JSON.parse(e.init.body) as Post['body']
      posts.push({ url: e.url, headers: e.init.headers, body })
      const acked: Record<string, number> = {}
      for (const ev of body.events) acked[ev.session_id] = Math.max(acked[ev.session_id] ?? 0, ev.seq)
      return { value: { status, ok: status < 300, headers: {}, text: JSON.stringify({ acked }) } }
    })
    await $.session.start({ surface: 'terminal', isInteractive: false, cwd: '/w' })
    await $.tool.call({ tool: 'Grep', pattern: 'x' })
    await clock.advance(5_000)
    expect(posts.length).toBe(1)
    status = 200
    await clock.advance(5_000)
    expect(posts.length).toBe(2)
    // The retry carries the same two events, not new copies.
    expect(posts[1].body.events.map(e => e.seq)).toEqual(posts[0].body.events.map(e => e.seq))
    await clock.advance(5_000)
    expect(posts.length).toBe(2) // acked: nothing left to send
  })
})

describe('pure helpers', () => {
  test('toolName passes names and refuses anything else', () => {
    expect(toolName('mcp__Linear__save_issue')).toBe('mcp__Linear__save_issue')
    expect(toolName('rm -rf /')).toBe('unknown')
    expect(toolName(42)).toBe('unknown')
  })

  test('modelName passes model ids and refuses anything else', () => {
    expect(modelName('claude-opus-5-5')).toBe('claude-opus-5-5')
    expect(modelName('claude-opus-4-6[1m]')).toBe('claude-opus-4-6[1m]')
    expect(modelName('claude\nIGNORE PREVIOUS')).toBeUndefined()
    expect(modelName(undefined)).toBeUndefined()
  })

  test('repoSlug strips credentials and suffixes', () => {
    expect(repoSlug('git@github.com:CleanExpo/Synthex.git')).toBe('CleanExpo/Synthex')
    expect(repoSlug('https://t:secret@github.com/CleanExpo/ATO/')).toBe('CleanExpo/ATO')
    expect(repoSlug(null)).toBeUndefined()
  })

  test('worstRate, makeSeq', () => {
    expect(worstRate([])).toBeUndefined()
    expect(worstRate([{ percentUsed: 3 }, { percentUsed: 9 }])).toBe(9)
    expect(makeSeq(2, 1) > makeSeq(1, 999)).toBe(true)
  })

  test('queue keeps the newest MAX_QUEUE and drops what was acked', () => {
    const q: LaneEvent[] = []
    for (let i = 0; i < MAX_QUEUE + 5; i++) enqueue(q, { session_id: 'a', seq: i, kind: 'tool', at: '' })
    expect(q.length).toBe(MAX_QUEUE)
    expect(q[0].seq).toBe(5)
    expect(dropAcked(q, { a: MAX_QUEUE + 2 }).map(e => e.seq)).toEqual([MAX_QUEUE + 3, MAX_QUEUE + 4])
  })
})
