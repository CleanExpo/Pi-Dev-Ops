// DegradedDataBanner — explicit warning rendered when a panel's live data
// fetch failed. Distinct from SourceBadge (the always-present source pip):
// this is the loud banner shown only on failure. Its only user, the provider
// cockpit, has no seed: it shows nothing, or its last successful reading.

export interface DegradedDataBannerProps {
  /** Which subsystem failed to respond. */
  source: string
  /** Optional machine-readable reason, e.g. 'control_panel_fetch_failed'. */
  reason?: string
}

export function DegradedDataBanner({ source, reason }: DegradedDataBannerProps) {
  return (
    <div
      role="alert"
      data-degraded-source={source}
      className="flex flex-col gap-1 px-5 py-3 font-mono text-[11px] leading-relaxed"
      style={{
        background: 'var(--cc-bg)',
        borderBottom: '1px solid var(--cc-grid)',
        borderLeft: '2px solid var(--cc-signal)',
      }}
    >
      <span className="uppercase tracking-[0.18em]" style={{ color: 'var(--cc-signal-text)' }}>
        Degraded data · {source}
      </span>
      <span style={{ color: 'var(--cc-ink-dim)' }}>
        Live request to {source} failed{reason ? ` (${reason})` : ''}. Any figures shown
        are from the last successful read, not current.
      </span>
    </div>
  )
}
