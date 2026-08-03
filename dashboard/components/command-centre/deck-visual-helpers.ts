// src/app/(founder)/founder/command-centre/deck-visual-helpers.ts
//
// Deck visual helpers — cut-pasted verbatim from page.tsx when the calm
// cockpit relocated the dense tiles onto sub-routes (UNI-2378), so the
// portfolio and knowledge pages share the same swatch / LED / rail logic
// the deck has always used. Purely presentational; no data access.

// Stable per-project accent (instrument swatch) — purely visual brand separation.
const BRAND_SWATCH: Record<string, string> = {
  'Unite-Hub': '#16a34a',
  RestoreAssist: '#34d399',
  Synthex: '#f97316',
  'Disaster-Recovery': '#fb7185',
  'DR-NRPG': '#f97316',
  'ATO-APP': '#facc15',
  'Dimitri-ITR': '#6366f1',
  'CCW-CRM': '#16a34a',
  'Authority-Site': '#16a34a',
  'Nexus-Hub': '#16a34a',
  'Pi-CEO-Dev': '#4ade80',
  CARSI: '#f97316',
}
export function swatchFor(name: string): string {
  if (BRAND_SWATCH[name]) return BRAND_SWATCH[name]
  let h = 0
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) % 360
  return `hsl(${h} 80% 62%)`
}

const RISK_RAIL: Record<string, string> = {
  read: '#16a34a',
  'write-local': '#34d399',
  'write-shared': '#fbbf24',
  external: '#fb923c',
  destructive: '#f87171',
}
export function railFor(risk: string): string {
  return RISK_RAIL[risk] ?? '#6f879b'
}

export function ledState(status: string): 'active' | 'stub' | 'idle' {
  if (status === 'active') return 'active'
  if (status === 'stub') return 'stub'
  return 'idle'
}

export function connectionLedState(state: string): 'active' | 'stub' | 'idle' {
  if (state === 'connected' || state === 'ready') return 'active'
  if (state === 'mock' || state === 'unknown') return 'stub'
  return 'idle'
}

export function hostOf(url?: string): string {
  return url ? url.replace(/^https?:\/\//, '').replace(/\/$/, '') : ''
}
