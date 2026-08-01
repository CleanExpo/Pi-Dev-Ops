// src/components/command-centre/DeckDetails.tsx
//
// Shared progressive-disclosure primitive for the command deck (founder
// feedback 14/07/2026: "a lot of exposed data that can be cleaned up").
// Summary row stays visible — title, one to three headline numbers, and a
// status badge slot — while the dense detail (identifier lists, rosters,
// forms) collapses behind a native <details> chevron. Pure presentation:
// no data fetching, no new dependencies, deck tokens only (OLED ground,
// mono accents, rounded-sm). Works in both server and client tiles.
//
// Note on identifiers: this page is founder-only behind the (founder)
// layout auth, so moving emails/ids/hostnames into the collapsed layer is
// visual de-clutter, not a security boundary — the expanded detail keeps
// them in full.

import styles from './deck-details.module.css'

export function DeckDetails({
  title,
  stats,
  badge,
  defaultOpen = false,
  testId,
  children,
}: {
  /** Always-visible tile title. */
  title: string
  /** 1–3 headline numbers / status words, e.g. "3 connected · 1 needs reauth". */
  stats?: React.ReactNode
  /** Status badge slot (usually a SourceBadge). Sits at the right edge. */
  badge?: React.ReactNode
  /** Render expanded on first paint (uncontrolled after that). */
  defaultOpen?: boolean
  testId?: string
  children: React.ReactNode
}) {
  return (
    <details className={styles.deckDetails} open={defaultOpen || undefined} data-testid={testId}>
      <summary className={styles.deckSummary}>
        <span aria-hidden className={styles.chev} />
        <span className={styles.title}>{title}</span>
        {stats != null && <span className={styles.stats}>{stats}</span>}
        {badge != null && <span className={styles.badge}>{badge}</span>}
      </summary>
      <div className={styles.body}>{children}</div>
    </details>
  )
}

/**
 * Honest "+N more" line for lists capped inside a disclosure. Renders
 * nothing when the list is fully shown, so callers can emit it
 * unconditionally after a `.slice(0, cap)`.
 */
export function DeckMoreLine({ total, shown }: { total: number; shown: number }) {
  if (total <= shown) return null
  return <p className={styles.moreLine}>+{total - shown} more not shown</p>
}

/** Default row cap for lists rendered inside a DeckDetails disclosure. */
export const DECK_LIST_CAP = 8

/** Row cap for full founder pages (summary-first cleanup, founder 14/07/2026). */
export const PAGE_LIST_CAP = 10

/**
 * The deck-details CSS falls back to dark-deck inks (#f0f3f7 text) when the
 * --deck-* / --cc-* tokens are absent — illegible on the founder app's light
 * (paper) theme. Founder pages outside the command deck spread this onto a
 * wrapping element so the primitive maps onto the app's light token set.
 * (DeckDetails lives under components/command-centre/; imported here rather
 * than duplicated — a later refactor can relocate it.)
 */
export const LIGHT_THEME_DECK_TOKENS = {
  '--deck-line': 'var(--color-border)',
  '--deck-line-soft': 'var(--color-border)',
  '--deck-text': 'var(--color-text-primary)',
  '--deck-muted': 'var(--color-text-muted)',
  '--deck-cyan-text': 'var(--color-accent-text)',
} as React.CSSProperties
