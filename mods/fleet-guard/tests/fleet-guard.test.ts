import { describe, expect, mock, test } from 'claude-code/testing'
import { decide, liveTeammates, modelAllowed, parseCap, parseModels } from '../hooks/fleet'

type Agent = { id: string; teammateId?: string; description: string; type: string; status: string }

const SPAWN = {
  tool_use_id: 'toolu_1',
  prompt: 'Review the diff.',
  description: 'review',
  subagentType: 'general-purpose',
  provider: { plugin: 'engine', tier: 'core' as const },
  parentModel: 'claude-opus-5-5',
  background: false,
  fork: false,
}
const TEAMMATE = { ...SPAWN, subagentType: 'teammate', isTeammate: true as const, name: 'scout', background: true }

function teammate(n: number, status: string): Agent {
  return { id: `t${n}`, teammateId: `scout-${n}@team`, description: 'scout', type: 'teammate', status }
}

/** Stubs what the mod calls; returns the spawns that reached Claude Code and the lines logged. */
function harness(on: any, opts: { env?: Record<string, string>; agents?: Agent[] | 'fail' } = {}) {
  const spawned: { model?: string; isTeammate?: boolean }[] = []
  const logs: string[] = []
  mock.env(on, opts.env ?? {})
  on('ui.log', ($: unknown, e: { text: string }) => {
    logs.push(e.text)
    return { value: undefined }
  })
  on('agent.list', () => (opts.agents === 'fail' ? { deny: 'list unavailable' } : { value: opts.agents ?? [] }))
  on('agent.spawn', ($: unknown, e: { model?: string; parentModel: string; isTeammate?: boolean }) => {
    spawned.push({ model: e.model, isTeammate: e.isTeammate })
    return { model: e.model ?? e.parentModel, agentId: `a${spawned.length}` }
  })
  return { spawned, logs }
}

describe('inert when unconfigured', () => {
  test('both variables unset: the spawn goes through unchanged', async ($, on) => {
    const { spawned, logs } = harness(on, { agents: [teammate(1, 'running'), teammate(2, 'running')] })
    const out = await $.agent.spawn({ ...TEAMMATE, model: 'opus' })
    expect(out.deny).toBeUndefined()
    expect(spawned).toEqual([{ model: 'opus', isTeammate: true }])
    expect(logs).toEqual([])
  })
})

describe('model allow list', () => {
  test('a model not on the list is rewritten to the first entry, with one log line', async ($, on) => {
    const { spawned, logs } = harness(on, { env: { FLEET_GUARD_MODELS: 'sonnet,haiku' } })
    const out = await $.agent.spawn({ ...SPAWN, model: 'opus' })
    expect(out.model).toBe('sonnet')
    expect(spawned).toEqual([{ model: 'sonnet', isTeammate: undefined }])
    expect(logs.length).toBe(1)
    expect(logs[0]).toMatch(/opus.*sonnet/)
  })

  test('a spawn naming no model is checked against the parent model', async ($, on) => {
    const { spawned } = harness(on, { env: { FLEET_GUARD_MODELS: 'haiku' } })
    await $.agent.spawn({ ...SPAWN })
    expect(spawned[0]?.model).toBe('haiku')
  })

  test('an allowed model passes untouched', async ($, on) => {
    const { spawned, logs } = harness(on, { env: { FLEET_GUARD_MODELS: 'sonnet,haiku' } })
    await $.agent.spawn({ ...SPAWN, model: 'claude-haiku-4-5' })
    expect(spawned[0]?.model).toBe('claude-haiku-4-5')
    expect(logs).toEqual([])
  })
})

describe('teammate cap', () => {
  test('at the cap a teammate is denied; idle and waiting teammates count', async ($, on) => {
    const agents = [teammate(1, 'running'), teammate(2, 'idle'), teammate(3, 'waiting'), teammate(4, 'completed')]
    const { spawned } = harness(on, { env: { FLEET_GUARD_MAX_TEAMMATES: '3' }, agents })
    const out = await $.agent.spawn({ ...TEAMMATE })
    expect(out.deny).toBe('fleet-guard: 3 teammates already running (cap 3)')
    expect(spawned).toEqual([])
  })

  test('below the cap a teammate starts', async ($, on) => {
    const { spawned } = harness(on, { env: { FLEET_GUARD_MAX_TEAMMATES: '3' }, agents: [teammate(1, 'running'), teammate(2, 'failed')] })
    const out = await $.agent.spawn({ ...TEAMMATE })
    expect(out.deny).toBeUndefined()
    expect(spawned.length).toBe(1)
  })

  test('subagents are not capped', async ($, on) => {
    const agents = [teammate(1, 'running'), teammate(2, 'running')]
    const { spawned } = harness(on, { env: { FLEET_GUARD_MAX_TEAMMATES: '1' }, agents })
    const out = await $.agent.spawn({ ...SPAWN })
    expect(out.deny).toBeUndefined()
    expect(spawned.length).toBe(1)
  })

  test('if the agent list fails, the teammate is allowed and the unknown count is logged', async ($, on) => {
    const { spawned, logs } = harness(on, { env: { FLEET_GUARD_MAX_TEAMMATES: '1' }, agents: 'fail' })
    const out = await $.agent.spawn({ ...TEAMMATE })
    expect(out.deny).toBeUndefined()
    expect(spawned.length).toBe(1)
    expect(logs.some(l => l.includes('teammate count unknown'))).toBe(true)
  })

  test('cap and model rules together: a teammate under the cap still gets an allowed model', async ($, on) => {
    const { spawned } = harness(on, { env: { FLEET_GUARD_MODELS: 'sonnet', FLEET_GUARD_MAX_TEAMMATES: '2' }, agents: [teammate(1, 'idle')] })
    await $.agent.spawn({ ...TEAMMATE, model: 'opus' })
    expect(spawned).toEqual([{ model: 'sonnet', isTeammate: true }])
  })
})

describe('pure decisions', () => {
  test('parseModels and parseCap', () => {
    expect(parseModels(undefined)).toBeNull()
    expect(parseModels(' , ')).toBeNull()
    expect(parseModels('Sonnet, haiku ,')).toEqual(['sonnet', 'haiku'])
    expect(parseCap(undefined)).toBeNull()
    expect(parseCap('')).toBeNull()
    expect(parseCap(' 4 ')).toBe(4)
    expect(parseCap('0')).toBe(0)
    expect(parseCap('-1')).toBe('invalid')
    expect(parseCap('two')).toBe('invalid')
  })

  test('modelAllowed matches ids, aliases and alias words of an id', () => {
    expect(modelAllowed('sonnet', ['sonnet'])).toBe(true)
    expect(modelAllowed('claude-sonnet-5-5', ['sonnet'])).toBe(true)
    expect(modelAllowed('CLAUDE-HAIKU-4-5', ['haiku'])).toBe(true)
    expect(modelAllowed('claude-opus-5-5', ['sonnet', 'haiku'])).toBe(false)
    expect(modelAllowed('sonnet', ['claude-sonnet-5-5'])).toBe(false)
  })

  test('liveTeammates counts pending, running, waiting and idle teammates only', () => {
    const agents = [
      teammate(1, 'pending'), teammate(2, 'running'), teammate(3, 'waiting'), teammate(4, 'idle'),
      teammate(5, 'completed'), teammate(6, 'failed'), teammate(7, 'killed'),
      { id: 's1', description: 'x', type: 'Explore', status: 'running' },
    ]
    expect(liveTeammates(agents)).toBe(4)
  })

  test('decide', () => {
    const base = { isTeammate: true, fork: false, parentModel: 'claude-opus-5-5' }
    expect(decide(base, { models: null, cap: null }, 9)).toEqual({ kind: 'pass' })
    expect(decide(base, { models: null, cap: 2 }, 2)).toEqual({ kind: 'deny', reason: 'fleet-guard: 2 teammates already running (cap 2)' })
    expect(decide(base, { models: null, cap: 0 }, 0).kind).toBe('deny')
    expect(decide(base, { models: null, cap: 2 }, null)).toEqual({ kind: 'pass' })
    expect(decide({ ...base, isTeammate: false }, { models: null, cap: 0 }, 5)).toEqual({ kind: 'pass' })
    expect(decide(base, { models: ['sonnet'], cap: null }, null)).toEqual({ kind: 'rewrite', model: 'sonnet', from: 'claude-opus-5-5' })
    expect(decide({ ...base, model: 'inherit' }, { models: ['opus'], cap: null }, null)).toEqual({ kind: 'pass' })
    expect(decide({ ...base, fork: true }, { models: ['sonnet'], cap: null }, null)).toEqual({ kind: 'pass' })
  })
})
