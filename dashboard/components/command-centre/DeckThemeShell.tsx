'use client'

// DeckThemeShell — client wrapper for the command deck's visual register.
// The deck page stays a Server Component; only the Feel flip (deck ↔
// daylight) is client state, persisted in the ui store. Daylight is the
// Affirm-inspired paper/indigo register (docs/design/mobbin-ui-library.md).
import { useEffect, useState, type ReactNode } from 'react'
import { useUIStore } from '@/store/ui'
import styles from './command-deck.module.css'
import shell from './shell.module.css'

export function DeckThemeShell({ className, children }: { className: string; children: ReactNode }) {
  const deckTheme = useUIStore((s) => s.deckTheme)
  const setDeckTheme = useUIStore((s) => s.setDeckTheme)
  // The persisted store rehydrates from localStorage before the first client
  // render, while the server rendered the default ('daylight') — a persisted
  // 'deck' preference therefore text-mismatches the SSR HTML (React #418 on
  // /operations, UNI-2378 E2E finding 6). Render the server default until
  // mounted; the persisted preference applies one frame later.
  const [hydrated, setHydrated] = useState(false)
  useEffect(() => setHydrated(true), [])
  const daylight = hydrated ? deckTheme === 'daylight' : true
  // cc-daylight is a global (unhashed) marker so nested CSS modules that keep
  // their own token scopes (command-centre .scope, pipeline .board) can
  // bridge into the daylight register.
  return (
    <div className={daylight ? `${className} ${styles.daylight} ${shell.daylight} cc-daylight` : className}>
      {children}
      <button
        type="button"
        className={styles.feelToggle}
        onClick={() => setDeckTheme(daylight ? 'deck' : 'daylight')}
        aria-pressed={daylight}
        data-testid="deck-feel-toggle"
      >
        Feel: {daylight ? 'Daylight' : 'Deck'}
      </button>
    </div>
  )
}
