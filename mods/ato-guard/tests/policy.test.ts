import { describe, expect, test } from 'claude-code/testing'
import { DEFAULT_ALLOW, parseAllow, refuseReason, rewritingHits } from '../hooks/policy'

function mod(name: string, events: string[], tier = 'user') {
  return { name, provenance: `${name}@pi-dev-ops-mods`, tier, events }
}

describe('rewritingHits', () => {
  test('exact events on the list', () => {
    for (const ev of ['tool.call', 'tool.check', 'tool.describe', 'classic.PreToolUse', 'classic.PostToolUse', 'engine.create', 'prompt.submit', 'prompt.section']) {
      expect(rewritingHits(ev)).toEqual([ev])
    }
  })

  test('events off the list hook nothing that matters', () => {
    for (const ev of ['session.start', 'session.measure', 'agent.spawn', 'ui.render', 'turn.complete', 'classic.Stop', 'fs.write', '!tool.describe']) {
      expect(rewritingHits(ev)).toEqual([])
    }
  })

  test('wildcards and matchers are expanded', () => {
    expect(rewritingHits('*').length).toBeGreaterThan(5)
    expect(rewritingHits('tool.*')).toEqual(['tool.call', 'tool.check', 'tool.describe'])
    expect(rewritingHits('classic.*')).toEqual(['classic.PreToolUse', 'classic.PostToolUse'])
    expect(rewritingHits('prompt.*')).toEqual(['prompt.*'])
    expect(rewritingHits('engine.*')).toEqual(['engine.create'])
    expect(rewritingHits('ui.*')).toEqual([])
    expect(rewritingHits('tool.call{tool=Bash}')).toEqual(['tool.call'])
  })
})

describe('refuseReason', () => {
  test('a mod that rewrites tool calls or prompts is refused, naming what it hooks', () => {
    const r = refuseReason(mod('rewriter', ['session.start', 'tool.call', 'prompt.submit']), [])
    expect(r).toMatch(/rewriter hooks tool\.call, prompt\.submit/)
  })

  test('a mod that only observes sessions loads', () => {
    expect(refuseReason(mod('synthex-main-status', ['session.start', 'ui.render']), DEFAULT_ALLOW)).toBeNull()
    expect(refuseReason(mod('fleet-guard', ['agent.spawn']), DEFAULT_ALLOW)).toBeNull()
  })

  test('mc-lane is allowed by default, for tool.call only', () => {
    const lane = mod('mc-lane', ['session.start', 'tool.call', 'session.measure', 'session.end'])
    expect(refuseReason(lane, DEFAULT_ALLOW)).toBeNull()
    expect(refuseReason({ ...lane, events: [...lane.events, 'tool.check'] }, DEFAULT_ALLOW)).toMatch(/hooks tool\.check/)
    const star = refuseReason({ ...lane, events: ['*'] }, DEFAULT_ALLOW)
    expect(star).toMatch(/hooks tool\.check, tool\.describe/)
    const named = (star ?? '').split(' hooks ')[1]?.split('. ')[0] ?? ''
    expect(named.split(', ')).not.toContain('tool.call')
    expect(named.split(', ')).toContain('prompt.*')
  })

  test('the allow list matches the name or the full id; an empty list allows nobody', () => {
    const lane = mod('mc-lane', ['tool.call'])
    expect(refuseReason(lane, ['mc-lane@pi-dev-ops-mods'])).toBeNull()
    expect(refuseReason(lane, parseAllow(''))).toMatch(/mc-lane hooks tool\.call/)
  })

  test('built-in mods always load; prepend and append mods are judged like users', () => {
    expect(refuseReason(mod('agents-md', ['prompt.context'], 'builtin'), [])).toBeNull()
    expect(refuseReason(mod('org-mod', ['tool.call'], 'prepend'), [])).not.toBeNull()
    expect(refuseReason(mod('org-mod', ['engine.create'], 'append'), [])).not.toBeNull()
  })

  test('parseAllow: unset is the default, a list is trimmed', () => {
    expect(parseAllow(undefined)).toEqual(['mc-lane'])
    expect(parseAllow(' mc-lane , other@market ,')).toEqual(['mc-lane', 'other@market'])
    expect(parseAllow('')).toEqual([])
  })
})
