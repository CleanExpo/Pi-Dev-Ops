// ato-guard — taxpayer-data guard for sessions in the ATO repository.
//
// Inert everywhere else: it acts only when $.session.repo()'s remote names the
// ATO repository (CleanExpo/ATO, or a name with "ato" as a whole word, such as
// ato-ai). In scope it does three things on every tool call:
//   1. Mask: lets the tool run, then masks TFNs, ABNs, BSB + account numbers and
//      Bearer/Xero tokens in its result before the model reads it (hooks/mask.ts).
//   2. Block: refuses Xero API writes and SBR/lodgement writes without running
//      them (hooks/guard.ts). Reads pass through untouched.
//   3. Audit: appends one line per masked or denied call to
//      ~/.ato-guard/audit.jsonl — names and counts only (hooks/audit.ts).
// No network, no credentials. An audit failure never breaks the tool call.
//
// Functions that take `$` are top-level declarations: the engine scans the
// module before loading it and refuses `$` handed to anything else.

import type { EngineInterface, Register } from 'claude-code'
import { AUDIT_DIR, AUDIT_FILE, auditLine, needsRoll, rollName } from './audit'
import { decide, isAtoRemote } from './guard'
import { maskValue, total, type Counts } from './mask'

// Module state. A reload starts it over, and scope is looked up again.
const st = {
  active: undefined as boolean | undefined,
  session: 'unknown',
}

async function inScope($: EngineInterface): Promise<boolean> {
  if (st.active !== undefined) return st.active
  let remote: string | null | undefined
  try {
    remote = (await $.session.repo())?.remote
  } catch {
    return false // not cached: the next call asks again
  }
  st.active = isAtoRemote(remote)
  if (st.active) {
    try {
      st.session = await $.session.id()
    } catch {
      st.session = 'unknown'
    }
  }
  return st.active
}

// Writes `text`, creating the audit directory the first time.
async function writeFile($: EngineInterface, dir: string, path: string, text: string): Promise<void> {
  try {
    await $.fs.write(path, text)
  } catch {
    await $.process.run(['mkdir', '-p', dir])
    await $.fs.write(path, text)
  }
}

// read → append → write; past ROLL_BYTES the old file moves to audit-<date>.jsonl.
async function audit($: EngineInterface, tool: string, decision: string, counts: Counts): Promise<void> {
  try {
    const home = await $.env.get('HOME')
    if (!home) return
    const dir = `${home.replace(/\/+$/, '')}/${AUDIT_DIR}`
    const path = `${dir}/${AUDIT_FILE}`
    const now = await $.clock.now()
    const line = auditLine({ at: new Date(now).toISOString(), session: st.session, tool, decision, counts })
    let current = (await $.fs.exists(path)) ? await $.fs.read(path) : ''
    if (needsRoll(current, line)) {
      let rolled = `${dir}/${rollName(now, false)}`
      if (await $.fs.exists(rolled)) rolled = `${dir}/${rollName(now, true)}`
      await $.fs.write(rolled, current)
      current = ''
    }
    await writeFile($, dir, path, current + line)
  } catch {
    // The audit is best-effort; the tool call it describes goes on regardless.
  }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    st.active = undefined
    return next(e)
  })

  on('tool.call', async ($, e, next) => {
    if (!(await inScope($))) return next(e)
    const tool = typeof e.tool === 'string' ? e.tool : ''
    const reason = decide(tool, e as unknown as Record<string, unknown>)
    if (reason !== null) {
      await audit($, tool, 'denied', {})
      return { deny: `ato-guard: ${reason}` }
    }
    const ran = await next(e)
    // A refused call never ran, so there is nothing to mask.
    if (ran.deny !== undefined || ran.result === undefined) return ran
    const counts: Counts = {}
    const result = maskValue(ran.result, counts)
    const n = total(counts)
    if (n === 0) return ran
    await audit($, tool, `masked:${n}`, counts)
    return { ...ran, result } as typeof ran
  })
}
