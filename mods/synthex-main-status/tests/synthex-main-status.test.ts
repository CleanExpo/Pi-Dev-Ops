import { describe, expect, mock, test } from 'claude-code/testing'
import { decideStatus, isSynthex, repoSlug } from '../hooks/status'

const SYNTHEX_REMOTE = 'https://x-token:abc@github.com/CleanExpo/Synthex.git'
const TICK = 120_000

type Answer = { exitCode: number; stdout: string; stderr: string } | { deny: string }

const runs = (conclusion: string, displayTitle = 'fix: build', status = 'completed') =>
  ({ exitCode: 0, stderr: '', stdout: JSON.stringify([{ conclusion, status, displayTitle, url: 'https://x/1' }]) })

/** Stubs what the mod calls. `next()` answers the next gh call; returns the recorded calls. */
function harness(on: any, remote: string | null, answers: Answer[]) {
  const clock = mock.clock(on, { now: 1_700_000_000_000 })
  const argvs: string[][] = []
  const timeouts: number[] = []
  const statuses: (string | undefined)[] = []
  let i = 0
  on('session.repo', () => ({ value: remote === null ? null : { root: '/w', remote, internal: false } }))
  on('session.start', () => ({ cwd: '/w' }))
  on('ui.status', ($: unknown, e: { text?: string }) => {
    statuses.push(e.text)
    return { value: undefined }
  })
  on('process.run', ($: unknown, e: { argv: string[]; init?: { timeoutMs?: number } }) => {
    argvs.push(e.argv)
    timeouts.push(e.init?.timeoutMs ?? -1)
    const a = answers[Math.min(i++, answers.length - 1)]
    return 'deny' in a ? { deny: a.deny } : { value: a }
  })
  return { clock, argvs, timeouts, statuses }
}

const start = ($: any) => $.session.start({ surface: 'terminal', isInteractive: true, cwd: '/w' })

describe('in a Synthex session', () => {
  test('red main shows the RED line, read with the exact gh call', async ($, on) => {
    const h = harness(on, SYNTHEX_REMOTE, [runs('failure', 'feat: SYN-1205 dashboard')])
    await start($)
    await h.clock.settle()
    expect(h.statuses).toEqual(['main is RED: feat: SYN-1205 dashboard'])
    expect(h.argvs[0]).toEqual(['gh', 'run', 'list', '--repo', 'CleanExpo/Synthex', '--branch', 'main',
      '--limit', '1', '--json', 'conclusion,status,displayTitle,url'])
    expect(h.timeouts[0]).toBe(20_000)
  })

  test('a later success clears the line', async ($, on) => {
    const h = harness(on, SYNTHEX_REMOTE, [runs('timed_out'), runs('success')])
    await start($)
    await h.clock.settle()
    await h.clock.advance(TICK)
    expect(h.statuses).toEqual(['main is RED: fix: build', undefined])
  })

  test('gh failing to run shows unknown and never clears', async ($, on) => {
    const h = harness(on, SYNTHEX_REMOTE, [runs('failure'), { deny: 'spawn gh ENOENT' }])
    await start($)
    await h.clock.settle()
    await h.clock.advance(TICK)
    await h.clock.advance(TICK)
    expect(h.statuses).toEqual(['main is RED: fix: build', 'main CI status unknown (gh not installed)'])
    expect(h.statuses).not.toContain(undefined)
  })

  test('the same state twice calls ui.status once', async ($, on) => {
    const h = harness(on, SYNTHEX_REMOTE, [runs('cancelled')])
    await start($)
    await h.clock.settle()
    await h.clock.advance(TICK)
    await h.clock.advance(TICK)
    expect(h.argvs.length).toBe(3)
    expect(h.statuses).toEqual(['main is RED: fix: build'])
  })
})

describe('elsewhere', () => {
  test('a non-Synthex repo starts no timer and runs nothing', async ($, on) => {
    const h = harness(on, 'git@github.com:CleanExpo/Pi-Dev-Ops.git', [runs('failure')])
    await start($)
    await h.clock.settle()
    await h.clock.advance(TICK * 3)
    expect(h.argvs.length).toBe(0)
    expect(h.statuses).toEqual([])
  })

  test('no repo at all runs nothing', async ($, on) => {
    const h = harness(on, null, [runs('failure')])
    await start($)
    await h.clock.advance(TICK * 2)
    expect(h.argvs.length).toBe(0)
  })
})

describe('decideStatus', () => {
  test('red conclusions and success', () => {
    expect(decideStatus(runs('failure', 'x'))).toBe('main is RED: x')
    expect(decideStatus(runs('cancelled', 'x'))).toBe('main is RED: x')
    expect(decideStatus(runs('timed_out', 'x'))).toBe('main is RED: x')
    expect(decideStatus(runs('success'))).toBeUndefined()
  })

  test('titles are cut to 50 characters on one line', () => {
    const s = decideStatus(runs('failure', 'a'.repeat(80) + '\nsecond line')) as string
    expect(s.length).toBe('main is RED: '.length + 50)
    expect(s).not.toContain('\n')
  })

  test('every unreadable state is unknown, never undefined', () => {
    const u = (reason: string) => `main CI status unknown (${reason})`
    expect(decideStatus(runs('', 'x', 'in_progress'))).toBe(u('run in progress'))
    expect(decideStatus({ exitCode: 4, stdout: '', stderr: 'To get started with GitHub CLI, please run:  gh auth login' }))
      .toBe(u('gh not signed in'))
    expect(decideStatus({ exitCode: 1, stdout: '', stderr: 'HTTP 502' })).toBe(u('gh exited 1'))
    expect(decideStatus({ exitCode: 0, stdout: '[]', stderr: '' })).toBe(u('no runs on main'))
    expect(decideStatus({ exitCode: 0, stdout: 'not json', stderr: '' })).toBe(u('unparseable gh output'))
    expect(decideStatus({ exitCode: 0, stdout: '{}', stderr: '' })).toBe(u('unparseable gh output'))
    expect(decideStatus({ error: 'process timed out after 20000ms' })).toBe(u('gh did not run'))
    expect(decideStatus(runs('skipped'))).toBe(u('conclusion skipped'))
  })

  test('repo matching', () => {
    expect(repoSlug('git@github.com:CleanExpo/Synthex.git')).toBe('CleanExpo/Synthex')
    expect(isSynthex(SYNTHEX_REMOTE)).toBe(true)
    expect(isSynthex('https://github.com/cleanexpo/synthex')).toBe(true)
    expect(isSynthex('https://github.com/CleanExpo/Synthex-Docs.git')).toBe(false)
    expect(isSynthex(undefined)).toBe(false)
    expect(isSynthex('https://other.example/CleanExpo/Synthex.git')).toBe(false)
    expect(isSynthex('https://notgithub.com/CleanExpo/Synthex.git')).toBe(false)
  })
})
