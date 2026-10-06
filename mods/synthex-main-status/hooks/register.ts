// synthex-main-status — a status line while CleanExpo/Synthex main CI is red.
//
// Why: Synthex main sat red for two weeks (SYN-1205 / SYN-1211) with nobody
// noticing. In a session whose repo is CleanExpo/Synthex this reads the latest
// `main` run with `gh run list` every two minutes (and once at start) and shows
// `main is RED: <title>` under the prompt until a run succeeds.
//
// Read-only: one `gh run list` per tick, nothing written anywhere. A read that
// fails (gh missing, not signed in, timeout, bad output) shows "unknown", never
// a cleared line — no line must only ever mean green.
//
// Functions that take `$` are top-level declarations: the engine scans the
// module before loading it and refuses `$` handed to anything else.

import type { EngineInterface, Register } from 'claude-code'
import { decideStatus, isSynthex, SYNTHEX, type GhResult } from './status'

const EVERY_MS = 120_000
const GH_TIMEOUT_MS = 20_000
const ARGV = [
  'gh', 'run', 'list', '--repo', SYNTHEX, '--branch', 'main', '--limit', '1',
  '--json', 'conclusion,status,displayTitle,url',
]

// Module state. A reload starts it over. `shown` is what the status line says
// now; undefined means no line.
const st = { shown: undefined as string | undefined, inFlight: false }

async function readMain($: EngineInterface): Promise<GhResult> {
  try {
    const r = await $.process.run(ARGV, { timeoutMs: GH_TIMEOUT_MS })
    return { exitCode: r.exitCode, stdout: r.stdout, stderr: r.stderr }
  } catch (err) {
    return { error: err instanceof Error ? err.message : String(err) }
  }
}

// One read at a time; a tick that lands while one is out is skipped.
async function check($: EngineInterface): Promise<void> {
  if (st.inFlight) return
  st.inFlight = true
  try {
    const want = decideStatus(await readMain($))
    if (want !== st.shown) {
      $.ui.status(want)
      st.shown = want
    }
  } finally {
    st.inFlight = false
  }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const repo = await $.session.repo()
    if (!isSynthex(repo?.remote)) return next(e)
    // First read right away, but off the start path so the session isn't held for gh.
    $.clock.after(0, () => check($))
    $.clock.every(EVERY_MS, () => check($))
    return next(e)
  })
}
