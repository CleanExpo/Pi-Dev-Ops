// lane_config.ts: where the Mission Control link settings come from. Pure: no `$`.
//
// Two byte-identical copies: mods/mission-control/hooks and mods/mc-lane/hooks. Each mod is
// installed as its own plugin and cannot import the other. tests/test_mods_lane_config_parity.py
// fails when they differ, so edit one and copy it over the other.
//
// WHY LAUNCHD. After a reboot the desktop app can start before the launch agent
// com.unite-group.mc-lane-env copies MC_LANE_* from ~/.zshenv into launchd (12/11/2026:
// app 11:59:45, agent 11:59:46). `launchctl setenv` never reaches a process that is already
// running, so that app's environment lacks the settings for its whole life while launchd holds
// them. Each mod therefore asks launchd itself (`/bin/launchctl getenv NAME`) whenever its own
// environment lacks the pair. No new store: launchd already holds what the agent put there.
//
// THE PAIR RULE. URL and secret always come from ONE place: the environment when it holds both,
// otherwise launchd when it holds both, otherwise nothing. A URL from one place sent with a
// secret from the other would send a secret to a server it was never meant for.
//
// NAMES ONLY. Nothing here returns or formats a value except pickLaneConfig, whose result goes
// straight into a request header. Diagnostics name which settings are set, never what they hold.

export const LAUNCHCTL = '/bin/launchctl'
/** launchctl answers in milliseconds; the engine's 30 s default would stall a tool call. */
export const LAUNCHCTL_TIMEOUT_MS = 3000

export type LaneVars = { url?: string; secret?: string; host?: string }
export type LaneSource = 'env' | 'launchd'
export type LaneConfig = { url: string; secret: string; host: string; source: LaneSource }
/** What launchd gave: its settings, or why they could not be read (an error's type name). */
export type LaunchdRead = { vars: LaneVars } | { error: string }

export function launchctlArgv(name: string): string[] {
  return [LAUNCHCTL, 'getenv', name]
}

/** A trimmed, non-empty value, or undefined. Blank means absent, never an empty secret. */
export function clean(v: unknown): string | undefined {
  if (typeof v !== 'string') return undefined
  const t = v.trim()
  return t === '' ? undefined : t
}

/**
 * One `launchctl getenv NAME` result as a value. An unset name prints nothing and still exits 0
 * (checked on the Mini, 12/11/2026), so empty output is absent, not an empty value. A non-zero
 * exit or more than one line is not a value either.
 */
export function fromLaunchctl(r: { exitCode: number; stdout: string } | null | undefined): string | undefined {
  if (!r || r.exitCode !== 0 || typeof r.stdout !== 'string') return undefined
  const out = r.stdout.endsWith('\n') ? r.stdout.slice(0, -1) : r.stdout
  if (out.includes('\n')) return undefined
  return clean(out)
}

const hasPair = (v: LaneVars | null | undefined): v is LaneVars & { url: string; secret: string } =>
  !!v && !!clean(v.url) && !!clean(v.secret)

/** The pair rule above. Host is a label only, so it may fall back to the other place. */
export function pickLaneConfig(env: LaneVars, launchd: LaneVars | null): LaneConfig | null {
  const host = (first: LaneVars, second: LaneVars | null) => clean(first.host) ?? clean(second?.host) ?? 'unknown'
  if (hasPair(env)) {
    return { url: clean(env.url)!.replace(/\/+$/, ''), secret: clean(env.secret)!, host: host(env, launchd), source: 'env' }
  }
  if (hasPair(launchd)) {
    return { url: clean(launchd.url)!.replace(/\/+$/, ''), secret: clean(launchd.secret)!, host: host(launchd, env), source: 'launchd' }
  }
  return null
}

const describe = (v: LaneVars) =>
  `URL ${clean(v.url) ? 'set' : 'unset'}, secret ${clean(v.secret) ? 'set' : 'unset'}`

/** Why there is no config, per place looked, by name only. */
export function notConfiguredDetail(env: LaneVars, launchd: LaunchdRead | null): string {
  const where =
    launchd === null ? 'launchd: not asked' : 'error' in launchd ? `launchd: unreadable (${launchd.error})` : `launchd: ${describe(launchd.vars)}`
  return `not configured: MC_LANE_URL / MC_LANE_SECRET (environment: ${describe(env)}; ${where})`
}
