// Pure helpers for synthex-main-status: no `$`, so they unit-test without the kit.
//
// The one rule: a status line that is absent means "main is green". So nothing
// but a run that completed with `success` may clear it. Every failure to read
// the run says "unknown", never nothing.

export const SYNTHEX = 'CleanExpo/Synthex'

/** What `$.process.run` resolved to, or the message it rejected with. */
export type GhResult =
  | { exitCode: number; stdout: string; stderr: string }
  | { error: string }

const RED = new Set(['failure', 'cancelled', 'timed_out'])
const TITLE_MAX = 50

/** `owner/name` from a git remote URL, or undefined. Copied from mods/mc-lane/hooks/lane.ts (mods are self-contained). */
export function repoSlug(remote: string | null | undefined): string | undefined {
  if (!remote) return undefined
  const m = /[:/]([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+?)(?:\.git)?\/?$/.exec(remote.trim())
  return m ? `${m[1]}/${m[2]}` : undefined
}

/** True only for a github.com remote whose owner/name is CleanExpo/Synthex (any case). */
export function isSynthex(remote: string | null | undefined): boolean {
  if (!remote || !/(^|[@/])github\.com[:/]/i.test(remote.trim())) return false
  return repoSlug(remote)?.toLowerCase() === SYNTHEX.toLowerCase()
}

const unknown = (reason: string): string => `main CI status unknown (${reason})`

function title(raw: unknown): string {
  const t = typeof raw === 'string' ? raw.replace(/\s+/g, ' ').trim() : ''
  if (!t) return '(untitled run)'
  return t.length > TITLE_MAX ? t.slice(0, TITLE_MAX - 1) + '…' : t
}

function failureReason(r: GhResult): string | undefined {
  if ('error' in r) return /ENOENT|not found|no such file/i.test(r.error) ? 'gh not installed' : 'gh did not run'
  if (r.exitCode === 0) return undefined
  if (/auth login|not logged|authenticat/i.test(r.stderr)) return 'gh not signed in'
  return `gh exited ${r.exitCode}`
}

/**
 * The status line for one `gh run list --json conclusion,status,displayTitle,url`
 * read: a RED line, an unknown line, or undefined (clear: main is green).
 */
export function decideStatus(r: GhResult): string | undefined {
  const failed = failureReason(r)
  if (failed) return unknown(failed)
  let runs: unknown
  try {
    runs = JSON.parse((r as { stdout: string }).stdout)
  } catch {
    return unknown('unparseable gh output')
  }
  if (!Array.isArray(runs)) return unknown('unparseable gh output')
  if (runs.length === 0) return unknown('no runs on main')
  const run = runs[0] as { conclusion?: unknown; status?: unknown; displayTitle?: unknown }
  if (run.status !== 'completed') return unknown('run in progress')
  const conclusion = typeof run.conclusion === 'string' ? run.conclusion : ''
  if (RED.has(conclusion)) return `main is RED: ${title(run.displayTitle)}`
  if (conclusion === 'success') return undefined
  return unknown(`conclusion ${conclusion || 'missing'}`)
}
