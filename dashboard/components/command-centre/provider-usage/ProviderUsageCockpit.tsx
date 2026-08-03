'use client'

// src/components/command-center/provider-usage/ProviderUsageCockpit.tsx
// UNI-2146 — Mission Control provider usage cockpit. Visual meters for each AI
// provider (Claude/MiniMax/Gemini/OpenAI/OpenRouter) + routing hints that shift
// when a provider is near-limit or blocked. Metadata only — never shows keys.

import { useEffect, useState } from 'react'
import type {
  ProviderCockpitPayload,
  ProviderCockpitEntry,
  PlanSeat,
  ProviderState,
  UseLane,
} from '@/lib/command-centre/provider-usage'
import { SourceBadge, type SourceMode } from '@/components/command-centre/SourceBadge'
import { DegradedDataBanner } from '@/components/command-centre/DegradedDataBanner'

const POLL_MS = 30000

const STATE_LABEL: Record<ProviderState, string> = {
  available: 'available',
  watching: 'watching',
  near_limit: 'near limit',
  blocked: 'blocked',
  unknown: 'unknown',
}

// Fill variant — bright signal, used for the usage-meter bar.
function stateColor(state: ProviderState): string {
  if (state === 'available') return 'var(--cc-ink)'
  if (state === 'watching') return 'var(--cc-ink-dim)'
  if (state === 'near_limit') return 'var(--cc-signal)'
  if (state === 'blocked') return 'var(--cc-signal)'
  return 'var(--cc-ink-hush)'
}

// Text variant — AA-safe darkened signal, used for the state label.
function stateTextColor(state: ProviderState): string {
  if (state === 'available') return 'var(--cc-ink)'
  if (state === 'watching') return 'var(--cc-ink-dim)'
  if (state === 'near_limit') return 'var(--cc-signal-text)'
  if (state === 'blocked') return 'var(--cc-signal-text)'
  return 'var(--cc-ink-hush)'
}

const LANE_LABEL: Record<UseLane, string> = {
  deep_reasoning: 'Deep reasoning',
  coding: 'Coding',
  video_media: 'Video / media',
  fast_drafting: 'Fast drafting',
  fallback_aggregator: 'Fallback aggregator',
}

function sourceMode(payload: ProviderCockpitPayload | null, loading: boolean, error: string | null): SourceMode {
  if (loading) return 'loading'
  if (error || !payload) return 'degraded'
  return 'live'
}

function ProviderMeter({ provider }: { provider: ProviderCockpitEntry }) {
  const color = stateColor(provider.state)
  const textColor = stateTextColor(provider.state)
  const pct = provider.usagePct ?? 0
  return (
    <div className="cc-provider-row" style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: '8px 0' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
        <span style={{ color: 'var(--cc-ink)', fontWeight: 600, fontSize: 13 }}>{provider.label}</span>
        <span
          data-testid={`provider-state-${provider.id}`}
          style={{ color: textColor, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.04em' }}
        >
          {STATE_LABEL[provider.state]}
        </span>
      </div>
      {/* usage meter */}
      <div
        role="meter"
        aria-label={`${provider.label} usage`}
        aria-valuenow={provider.usagePct ?? undefined}
        aria-valuemin={0}
        aria-valuemax={100}
        style={{ height: 6, borderRadius: 2, background: 'var(--cc-ink-hush)', overflow: 'hidden' }}
      >
        <div style={{ width: `${pct}%`, height: '100%', background: color }} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--cc-ink-dim)' }}>
        <span>
          {provider.planType} · {provider.truthLevel}
          {provider.usagePct !== null ? ` · ${provider.usagePct}%` : ''}
        </span>
        <span>resets {provider.resetCadence}</span>
      </div>
      {provider.missingSetupReason && (
        <span style={{ fontSize: 11, color: 'var(--cc-signal-text)' }}>⚠ {provider.missingSetupReason}</span>
      )}
      {/* UNI-2338 — per-seat plan bars. usagePct null renders as "no telemetry",
          never a fabricated fill. */}
      {provider.plans && provider.plans.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3, paddingLeft: 10, marginTop: 2 }}>
          {provider.plans.map((seat) => (
            <PlanSeatBar key={seat.id} seat={seat} />
          ))}
        </div>
      )}
    </div>
  )
}

function PlanSeatBar({ seat }: { seat: PlanSeat }) {
  const pct = seat.usagePct ?? 0
  return (
    <div data-testid={`plan-seat-${seat.id}`} style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
        <span style={{ color: 'var(--cc-ink-dim)' }}>{seat.label}</span>
        <span style={{ color: stateTextColor(seat.state), textTransform: 'uppercase', letterSpacing: '0.04em' }}>
          {STATE_LABEL[seat.state]}
          {seat.usagePct !== null ? ` · ${seat.usagePct}%` : ' · no telemetry'}
        </span>
      </div>
      <div
        role="meter"
        aria-label={`${seat.label} plan usage`}
        aria-valuenow={seat.usagePct ?? undefined}
        aria-valuemin={0}
        aria-valuemax={100}
        style={{ height: 4, borderRadius: 2, background: 'var(--cc-ink-hush)', overflow: 'hidden' }}
      >
        <div style={{ width: `${pct}%`, height: '100%', background: stateColor(seat.state) }} />
      </div>
    </div>
  )
}

export function ProviderUsageCockpit() {
  const [payload, setPayload] = useState<ProviderCockpitPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)
      try {
        const res = await fetch('/api/command-centre/provider-usage', { cache: 'no-store' })
        if (!res.ok) throw new Error(`provider_usage_http_${res.status}`)
        const body = (await res.json()) as ProviderCockpitPayload
        if (!cancelled) {
          setPayload(body)
          setError(null)
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'provider_usage_failed')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    const timer = setInterval(load, POLL_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  return (
    <section className="cc-provider-cockpit" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ color: 'var(--cc-ink)', fontSize: 13, fontWeight: 600, margin: 0 }}>Provider usage</h3>
        <SourceBadge
          mode={sourceMode(payload, loading, error)}
          label={payload ? `${payload.summary.total} providers` : 'provider usage'}
          lastUpdatedAt={payload?.generatedAt}
        />
      </header>

      {error && <DegradedDataBanner source="Provider usage" reason={error} />}

      {payload && (
        <>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, fontSize: 11, color: 'var(--cc-ink-dim)' }}>
            <span>{payload.summary.available} available</span>
            <span>{payload.summary.watching} watching</span>
            <span style={{ color: 'var(--cc-signal-text)' }}>{payload.summary.nearLimit} near limit</span>
            <span style={{ color: 'var(--cc-signal-text)' }}>{payload.summary.blocked} blocked</span>
            <span>{payload.summary.unknown} unknown</span>
          </div>

          <div>
            {payload.providers.map((p) => (
              <ProviderMeter key={p.id} provider={p} />
            ))}
          </div>

          {/* Routing hints — shift when a provider is near-limit/blocked */}
          <div style={{ borderTop: '1px solid var(--cc-ink-hush)', paddingTop: 8 }}>
            <span style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <span style={{ fontSize: 11, color: 'var(--cc-ink-dim)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Routing
              </span>
              {/* UNI-2338 — MoA badge derived from the live routing payload only. */}
              <span
                data-testid="moa-routing-badge"
                style={{
                  fontSize: 10,
                  color: payload.routing.every((r) => r.recommended) ? 'var(--cc-ink)' : 'var(--cc-signal-text)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                }}
              >
                MoA {payload.routing.filter((r) => r.recommended).length}/{payload.routing.length} lanes routable
              </span>
            </span>
            <ul style={{ listStyle: 'none', margin: '4px 0 0', padding: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
              {payload.routing.map((r) => (
                <li key={r.lane} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                  <span style={{ color: 'var(--cc-ink-dim)' }}>{LANE_LABEL[r.lane]}</span>
                  <span style={{ color: r.recommended ? 'var(--cc-ink)' : 'var(--cc-signal-text)' }}>
                    {r.recommended ?? 'no provider'} <span style={{ color: 'var(--cc-ink-hush)' }}>· {r.reason}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </section>
  )
}
