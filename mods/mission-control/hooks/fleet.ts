// Pure helpers for mission-control: no `$`, so they unit-test without the kit.
//
// THE ONE RULE. A read that failed — transport error, 401, an HTML error page,
// JSON that is not the snapshot, or a snapshot the server itself marks
// `degraded` — must never come back looking like a healthy fleet. An empty
// machine list with no banner means "nobody has joined", so a broken read is
// `state: 'unknown'` (or `'degraded'`) with the reason, never `machines: []`
// on its own. Server side: app/server/mesh_fleet.py snapshot().

/** What one GET /api/mesh/fleet produced: an HTTP answer, or a transport error. */
export type FleetRead = { status: number; text: string } | { error: string }

export type MachineRow = {
  host: string
  status: string
  /** Seconds since the last heartbeat, or null when last_seen is missing or unparseable. */
  ageS: number | null
  /** The view's is_stale (no heartbeat in 60 s), an age over 60 s, or no age at all. */
  stale: boolean
  /** Drawn red: stale, runner-down or offline. */
  alert: boolean
  activeAgents: number | null
}

export type ShipRow = {
  machine: string
  repo: string
  subject: string
  sha: string
  ageS: number | null
}

export type Summary = {
  /** ok: a full, trusted snapshot. degraded: the server says a source failed. unknown: no usable snapshot. */
  state: 'ok' | 'degraded' | 'unknown'
  /** Why the state is not ok. */
  reason?: string
  machines: MachineRow[]
  /** Open (claimed or working) claims, or null when unknown. */
  openClaims: number | null
  recentShips: ShipRow[]
  degraded: boolean
  errors: string[]
}

export const RECENT_SHIPS = 5
export const STALE_AFTER_S = 60
const DOWN = new Set(['runner-down', 'offline'])

const str = (v: unknown, max = 80): string =>
  typeof v === 'string' ? v.replace(/\s+/g, ' ').trim().slice(0, max) : ''

function ageSeconds(iso: unknown, nowMs: number): number | null {
  if (typeof iso !== 'string') return null
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return null
  return Math.max(0, Math.round((nowMs - t) / 1000))
}

/** A read that produced no usable snapshot. Never an empty healthy fleet. */
export function unknown(reason: string): Summary {
  return { state: 'unknown', reason, machines: [], openClaims: null, recentShips: [], degraded: true, errors: [reason] }
}

function machineRow(r: Record<string, unknown>, nowMs: number): MachineRow {
  const status = str(r.status, 32) || 'unknown'
  const ageS = ageSeconds(r.last_seen, nowMs)
  const stale = r.is_stale === true || ageS === null || ageS > STALE_AFTER_S
  return {
    host: str(r.host, 64) || '?',
    status,
    ageS,
    stale,
    alert: stale || DOWN.has(status),
    activeAgents: typeof r.active_agents === 'number' ? r.active_agents : null,
  }
}

function shipRow(r: Record<string, unknown>, nowMs: number): ShipRow {
  return {
    machine: str(r.machine, 64),
    repo: str(r.repo, 64),
    subject: str(r.subject, 72),
    sha: str(r.sha, 7),
    ageS: ageSeconds(r.shipped_at, nowMs),
  }
}

function errorText(e: unknown): string {
  if (e && typeof e === 'object') {
    const o = e as Record<string, unknown>
    const parts = [str(o.source, 32), str(o.reason, 32), typeof o.status === 'number' ? String(o.status) : '']
    return parts.filter(Boolean).join(' ') || 'error'
  }
  return str(e, 64) || 'error'
}

const rowsOf = (v: unknown): Record<string, unknown>[] | null =>
  Array.isArray(v) ? v.filter((x): x is Record<string, unknown> => !!x && typeof x === 'object') : null

/** Turns one fleet read into what the pane and the tool show. */
export function summarize(read: FleetRead, nowMs: number): Summary {
  if ('error' in read) return unknown(`request failed: ${str(read.error, 80) || 'error'}`)
  if (read.status === 401 || read.status === 403) return unknown(`HTTP ${read.status}: secret refused`)
  if (read.status < 200 || read.status >= 300) return unknown(`HTTP ${read.status}`)

  let data: unknown
  try {
    data = JSON.parse(read.text)
  } catch {
    return unknown('response is not JSON')
  }
  if (!data || typeof data !== 'object' || Array.isArray(data)) return unknown('response is not a fleet snapshot')
  const d = data as Record<string, unknown>
  const machines = rowsOf(d.machines)
  const claims = rowsOf(d.claims)
  const ships = rowsOf(d.ships)
  if (!machines || !claims || !ships || typeof d.degraded !== 'boolean') {
    return unknown('response is not a fleet snapshot')
  }

  const errors = Array.isArray(d.errors) ? d.errors.map(errorText) : []
  const degraded = d.degraded || errors.length > 0
  const sum: Summary = {
    state: degraded ? 'degraded' : 'ok',
    machines: machines.map(r => machineRow(r, nowMs)),
    openClaims: claims.length,
    recentShips: ships.slice(0, RECENT_SHIPS).map(r => shipRow(r, nowMs)),
    degraded,
    errors,
  }
  if (degraded) {
    sum.reason = errors.length ? `server degraded: ${errors.join(', ')}` : 'server degraded'
    // A failed source arrives as an empty list; that empty list is not a count of zero.
    if (errors.some(e => e.startsWith('claims'))) sum.openClaims = null
  }
  return sum
}

/** "12s", "4m", "3h", "2d", or "?": a heartbeat age short enough for one row. */
export function formatAge(s: number | null): string {
  if (s === null) return '?'
  if (s < 120) return `${s}s`
  if (s < 7200) return `${Math.round(s / 60)}m`
  if (s < 172_800) return `${Math.round(s / 3600)}h`
  return `${Math.round(s / 86_400)}d`
}
