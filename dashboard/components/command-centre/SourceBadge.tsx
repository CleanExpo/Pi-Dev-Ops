// SourceBadge — universal data-source metadata pip for Command Center panels.
//
// Tells the operator whether a value is fresh from a system of record, a
// static seed, mid-fetch, or a stale fallback. Single rendering primitive
// every panel embeds — a SourceMode union keeps panels from inventing rogue
// values, so seed numbers can never be silently dressed as live.
//
//   - 'live'      — values come from an API request that succeeded this session.
//   - 'seed'      — values come from a hand-curated TS seed in this repo.
//   - 'loading'   — request in flight; no value to trust yet.
//   - 'degraded'  — request attempted, fetch failed; rendering a fallback seed.

export type SourceMode = 'live' | 'seed' | 'loading' | 'degraded'

export interface SourceBadgeProps {
  /** Classification of the underlying data. */
  mode: SourceMode
  /** Short human label, e.g. "CC · 7 tasks" or "seed v1". */
  label: string
  /** ISO timestamp of the last data refresh. Only rendered for 'live'. */
  lastUpdatedAt?: string
}

const MODE_LABEL: Record<SourceMode, string> = {
  live: 'live',
  seed: 'seed',
  loading: 'loading',
  degraded: 'degraded',
}

// 'degraded' is a warning, not an alert — amber family (matches the deck's
// own --deck-amber tokens), not the cc-signal green/red. Dot uses the bright
// fill; text uses the AA-passing darkened variant.
function dotColorFor(mode: SourceMode): string {
  if (mode === 'live') return 'var(--cc-ink, #cfe0ec)'
  if (mode === 'degraded') return 'var(--deck-amber, #f4820f)'
  return 'var(--cc-ink-hush, rgba(207,224,236,0.45))'
}

function textColorFor(mode: SourceMode): string {
  if (mode === 'live') return 'var(--cc-ink, #cfe0ec)'
  if (mode === 'degraded') return 'var(--deck-amber-text, #b45309)'
  return 'var(--cc-ink-hush, rgba(207,224,236,0.45))'
}

function formatTimestamp(iso: string): string | null {
  const parsed = Date.parse(iso)
  if (Number.isNaN(parsed)) return null
  const now = Date.now()
  const deltaSec = Math.max(0, Math.round((now - parsed) / 1000))
  if (deltaSec < 60) return `${deltaSec}s ago`
  if (deltaSec < 3600) return `${Math.round(deltaSec / 60)}m ago`
  if (deltaSec < 86400) return `${Math.round(deltaSec / 3600)}h ago`
  return `${Math.round(deltaSec / 86400)}d ago`
}

export function SourceBadge({ mode, label, lastUpdatedAt }: SourceBadgeProps) {
  const dotColor = dotColorFor(mode)
  const textColor = textColorFor(mode)
  const stamp = mode === 'live' && lastUpdatedAt ? formatTimestamp(lastUpdatedAt) : null
  return (
    <span
      data-source-mode={mode}
      className="inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.18em]"
      style={{ color: 'var(--cc-ink-hush, rgba(207,224,236,0.45))' }}
      aria-label={`Source: ${MODE_LABEL[mode]}. ${label}${stamp ? `. Updated ${stamp}.` : ''}`}
    >
      <span
        aria-hidden
        style={{
          display: 'inline-block',
          width: 6,
          height: 6,
          borderRadius: '50%',
          background: dotColor,
        }}
      />
      <span style={{ color: textColor }}>{MODE_LABEL[mode]}</span>
      <span>·</span>
      <span style={{ color: 'var(--cc-ink-dim, #6f879b)' }}>{label}</span>
      {stamp && (
        <>
          <span>·</span>
          <span style={{ color: 'var(--cc-ink-hush, rgba(207,224,236,0.45))' }}>{stamp}</span>
        </>
      )}
    </span>
  )
}
