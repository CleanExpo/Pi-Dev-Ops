// Pure audit-line helpers for ato-guard: no `$`, so they unit-test without the kit.
//
// WHAT IS WRITTEN. One JSON line per guarded decision: when, which session,
// which tool, the decision (`masked:<n>` or `denied`) and how many of each kind
// were masked. Never the tool's input, its output or the matched text — the
// audit file must be safe to keep, copy and show.

import type { Counts, Kind } from './mask'

/** `$.fs.read`/`$.fs.write` refuse files over 4 MiB, so roll well before that. */
export const ROLL_BYTES = 3 * 1024 * 1024

export const AUDIT_DIR = '.ato-guard'
export const AUDIT_FILE = 'audit.jsonl'

export type AuditEntry = {
  at: string
  session: string
  tool: string
  decision: string
  counts: Counts
}

const TOOL_NAME = /^[A-Za-z0-9_.:-]{1,128}$/
const SESSION_ID = /^[A-Za-z0-9_-]{1,128}$/
const KINDS: readonly Kind[] = ['TFN', 'ABN', 'BANK', 'TOKEN']

/** A tool's name as the audit may hold it; anything that is not a name becomes 'unknown'. */
export function toolName(raw: unknown): string {
  return typeof raw === 'string' && TOOL_NAME.test(raw) ? raw : 'unknown'
}

/** The line to append, newline included. Only known fields, and only whole numbers in counts. */
export function auditLine(entry: AuditEntry): string {
  const counts: Counts = {}
  for (const k of KINDS) {
    const n = entry.counts[k]
    if (typeof n === 'number' && Number.isInteger(n) && n > 0) counts[k] = n
  }
  return JSON.stringify({
    at: entry.at,
    session: SESSION_ID.test(entry.session) ? entry.session : 'unknown',
    tool: toolName(entry.tool),
    decision: /^(?:denied|masked:\d+)$/.test(entry.decision) ? entry.decision : 'unknown',
    counts,
  }) + '\n'
}

/** UTF-8 size of a string, which is what the 4 MiB limit counts. */
export function byteLength(text: string): number {
  return new TextEncoder().encode(text).length
}

/** True when appending `line` would take the file past ROLL_BYTES. */
export function needsRoll(current: string, line: string): boolean {
  return current.length > 0 && byteLength(current) + byteLength(line) > ROLL_BYTES
}

/** `audit-2026-10-06.jsonl`, or with the time too when that day's file already exists. */
export function rollName(nowMs: number, withTime: boolean): string {
  const iso = new Date(nowMs).toISOString()
  const stamp = withTime ? iso.slice(0, 19).replace(/:/g, '-') : iso.slice(0, 10)
  return `audit-${stamp}.jsonl`
}
