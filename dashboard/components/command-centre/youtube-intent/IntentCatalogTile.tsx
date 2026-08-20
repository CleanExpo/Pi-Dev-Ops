'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { SourceBadge, type SourceMode } from '@/components/command-centre/SourceBadge'

type IntentSummary = {
  updatedAt: string | null
  acceptedCount: number
  excludedCount: number
  topics: Array<{ topic: string; frequency_score: number }>
  boardUrl: string
}

export function IntentCatalogTile() {
  const [summary, setSummary] = useState<IntentSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    async function load() {
      try {
        const res = await fetch('/api/command-centre/youtube-intent')
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = (await res.json()) as IntentSummary
        if (alive) {
          setSummary(data)
          setError(null)
        }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : 'load failed')
      } finally {
        if (alive) setLoading(false)
      }
    }
    load()
    return () => {
      alive = false
    }
  }, [])

  const mode: SourceMode = loading ? 'loading' : error || !summary ? 'degraded' : 'live'

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ color: 'var(--deck-text)', fontSize: 14, fontWeight: 700, margin: 0 }}>YouTube Intent Catalog</h3>
        <SourceBadge mode={mode} label="UG-N Signals" lastUpdatedAt={summary?.updatedAt ?? undefined} />
      </div>

      {error ? (
        <p style={{ color: 'var(--deck-abort-text)', fontSize: 12, margin: 0 }}>
          Could not load intent catalog: {error}
        </p>
      ) : (
        <p style={{ color: 'var(--deck-muted)', fontSize: 12, margin: 0 }}>
          <b style={{ color: 'var(--deck-text)' }}>{summary?.acceptedCount ?? 0}</b> strategic signals ·{' '}
          <b style={{ color: 'var(--deck-text)' }}>{summary?.excludedCount ?? 0}</b> excluded
        </p>
      )}

      <p style={{ color: 'var(--deck-muted)', fontSize: 12, margin: 0 }}>
        Top topics: {(summary?.topics ?? []).slice(0, 3).map((t) => t.topic).join(', ') || 'none yet'}
      </p>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <Link
          href="/command-centre/youtube-intent"
          style={{
            fontSize: 12,
            padding: '5px 12px',
            borderRadius: 2,
            border: '1px solid var(--deck-line)',
            color: 'var(--deck-cyan-text)',
            textDecoration: 'none',
          }}
        >
          Open catalog →
        </Link>
        <a
          href={summary?.boardUrl ?? 'http://localhost:7119'}
          target="_blank"
          rel="noreferrer"
          style={{
            fontSize: 12,
            padding: '5px 12px',
            borderRadius: 2,
            border: '1px solid var(--deck-line)',
            color: 'var(--deck-cyan-text)',
            textDecoration: 'none',
          }}
        >
          Open Excalidraw board
        </a>
      </div>
    </section>
  )
}
