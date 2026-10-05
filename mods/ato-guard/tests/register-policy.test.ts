// ato-guard as an organization's first mod (managed prependPlugins), judging
// the mods that load after it. See README "Refuse tool-rewriting mods".
import { describe, expect, mock, test, tier } from 'claude-code/testing'

tier('prepend')

const ATO = 'https://github.com/CleanExpo/ATO.git'

// Inline mods are self-contained: each answers the tool call itself, which
// shows that it loaded.
const rewriter = {
  name: 'rewriter',
  register(on: any) {
    on('tool.call', async () => ({ result: 'rewriter answered' }))
  },
}
const promptMod = {
  name: 'prompt-mod',
  register(on: any) {
    on('prompt.submit', async ($: unknown, e: unknown, next: (e: unknown) => unknown) => next(e))
  },
}
const lane = {
  name: 'mc-lane',
  register(on: any) {
    on('tool.call', async () => ({ result: 'mc-lane answered' }))
  },
}
const laneChecker = {
  name: 'mc-lane',
  register(on: any) {
    on('tool.check', async () => ({ decision: 'allow' }))
    on('tool.call', async () => ({ result: 'mc-lane answered' }))
  },
}
const builtinRewriter = {
  name: 'built-in-thing',
  tier: 'builtin' as const,
  register(on: any) {
    on('tool.call', async () => ({ result: 'builtin answered' }))
  },
}

function harness(on: any, remote: string | null, env: Record<string, string> = {}) {
  mock.clock(on, { now: 1_700_000_000_000 })
  mock.env(on, { HOME: '/home/test', ...env })
  on('session.id', () => ({ value: 'sess-1' }))
  on('session.repo', () => ({ value: remote === null ? null : { root: '/w', remote, internal: false } }))
  on('tool.call', () => ({ result: 'claude code answered' }))
}

async function refusal($: any): Promise<string> {
  try {
    await $.tool.call({ tool: 'Read', file_path: 'README.md' })
  } catch (error) {
    return (error as Error).message
  }
  return ''
}

describe('in the ATO repository', () => {
  test('a mod that hooks tool.call is refused before it loads', { plugins: [rewriter] }, async ($, on) => {
    harness(on, ATO)
    expect(await refusal($)).toMatch(/^rewriter: refused by ato-guard: in the ATO repository .*rewriter hooks tool\.call/)
  })

  test('a mod that hooks prompt.submit is refused', { plugins: [promptMod] }, async ($, on) => {
    harness(on, ATO)
    expect(await refusal($)).toMatch(/^prompt-mod: refused by ato-guard: .*hooks prompt\.submit/)
  })

  test('mc-lane loads by default: it only reads tool calls', { plugins: [lane] }, async ($, on) => {
    harness(on, ATO)
    const out = await $.tool.call({ tool: 'Read', file_path: 'README.md' })
    expect(out).toEqual({ result: 'mc-lane answered' })
  })

  test('mc-lane is refused when ATO_GUARD_ALLOW_MODS is set empty', { plugins: [lane] }, async ($, on) => {
    harness(on, ATO, { ATO_GUARD_ALLOW_MODS: '' })
    expect(await refusal($)).toMatch(/^mc-lane: refused by ato-guard: .*mc-lane hooks tool\.call/)
  })

  test('an allowed mod that also hooks tool.check is refused', { plugins: [laneChecker] }, async ($, on) => {
    harness(on, ATO)
    expect(await refusal($)).toMatch(/^mc-lane: refused by ato-guard: .*hooks tool\.check/)
  })

  test('a built-in mod is never refused', { plugins: [builtinRewriter] }, async ($, on) => {
    harness(on, ATO)
    const out = await $.tool.call({ tool: 'Read', file_path: 'README.md' })
    expect(out).toEqual({ result: 'builtin answered' })
  })
})

describe('outside the ATO repository', () => {
  test('a tool-rewriting mod loads', { plugins: [rewriter] }, async ($, on) => {
    harness(on, 'https://github.com/CleanExpo/Synthex.git')
    const out = await $.tool.call({ tool: 'Read', file_path: 'README.md' })
    expect(out).toEqual({ result: 'rewriter answered' })
  })

  test('no repository: a tool-rewriting mod loads', { plugins: [rewriter] }, async ($, on) => {
    harness(on, null)
    const out = await $.tool.call({ tool: 'Read', file_path: 'README.md' })
    expect(out).toEqual({ result: 'rewriter answered' })
  })
})
