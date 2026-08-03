// src/store/ui.ts
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type Theme = 'dark' | 'light'
// Command-deck visual register: 'daylight' (Affirm-inspired paper/indigo —
// see docs/design/mobbin-ui-library.md; default per founder directive 15/07)
// or 'deck' (flight-deck dark, opt-in via the Feel toggle).
type DeckTheme = 'deck' | 'daylight'

interface UIStore {
  sidebarOpen: boolean
  expandedBusinesses: string[]
  theme: Theme
  deckTheme: DeckTheme
  captureOpen: boolean
  commandBarOpen: boolean
  toggleSidebar: () => void
  toggleBusiness: (key: string) => void
  setTheme: (theme: Theme) => void
  setDeckTheme: (deckTheme: DeckTheme) => void
  toggleCapture: () => void
  toggleCommandBar: () => void
}

export const useUIStore = create<UIStore>()(
  persist(
    (set) => ({
      sidebarOpen: true,
      expandedBusinesses: [],
      theme: 'light',
      deckTheme: 'daylight',
      captureOpen: false,
      commandBarOpen: false,
      toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
      toggleBusiness: (key) =>
        set((s) => ({
          expandedBusinesses: s.expandedBusinesses.includes(key)
            ? s.expandedBusinesses.filter((k) => k !== key)
            : [...s.expandedBusinesses, key],
        })),
      setTheme: (theme) => set({ theme }),
      setDeckTheme: (deckTheme) => set({ deckTheme }),
      toggleCapture: () => set((s) => ({ captureOpen: !s.captureOpen })),
      toggleCommandBar: () => set((s) => ({ commandBarOpen: !s.commandBarOpen })),
    }),
    {
      name: 'nexus-ui',
      // v1: daylight became the default register (founder directive 15/07).
      // Migrate v0 stores so machines that persisted 'deck' before the flip
      // see daylight once; any Feel-toggle choice made after this persists.
      version: 1,
      migrate: (persisted, version) => {
        const state = persisted as {
          sidebarOpen: boolean
          expandedBusinesses: string[]
          theme: Theme
          deckTheme: DeckTheme
        }
        if (version < 1) return { ...state, deckTheme: 'daylight' as const }
        return state
      },
      // commandBarOpen intentionally excluded — always starts closed
      partialize: (s) => ({
        sidebarOpen: s.sidebarOpen,
        expandedBusinesses: s.expandedBusinesses,
        theme: s.theme,
        deckTheme: s.deckTheme,
      }),
    }
  )
)
