'use client'

// src/components/command-centre/wiki-graph/WikiGraphTile.tsx
//
// Command-deck tile for the Wiki Graph View (UNI-2304). Client-fetches the
// founder-scoped graph summary and links to the full interactive page.
// Error-contained: a failed fetch degrades to an honest message, never a fake
// count.

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { SourceBadge, type SourceMode } from '@/components/command-centre/SourceBadge'

interface GraphSummary {
  pageCount: number
  edgeCount: number
  lastSync: string | null
}

export function WikiGraphTile() {
  const [summary, setSummary] = useState<GraphSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    async function load() {
      try {
        const res = await fetch('/api/command-centre/wiki-graph')
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = (await res.json()) as GraphSummary
        if (alive) {
          setSummary({ pageCount: data.pageCount, edgeCount: data.edgeCount, lastSync: data.lastSync })
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
        <h3 style={{ color: 'var(--deck-text)', fontSize: 14, fontWeight: 700, margin: 0 }}>Wiki Graph</h3>
        <SourceBadge mode={mode} label="Wiki" lastUpdatedAt={summary?.lastSync ?? undefined} />
      </div>

      {error ? (
        <p style={{ color: 'var(--deck-abort-text)', fontSize: 12, margin: 0 }}>Could not load wiki graph: {error}</p>
      ) : (
        <p style={{ color: 'var(--deck-muted)', fontSize: 12, margin: 0 }}>
          <b style={{ color: 'var(--deck-text)' }}>{summary?.pageCount ?? 0}</b> pages ·{' '}
          <b style={{ color: 'var(--deck-text)' }}>{summary?.edgeCount ?? 0}</b> links in the knowledge base
        </p>
      )}

      <Link
        href="/command-centre/wiki-graph"
        style={{
          alignSelf: 'flex-start',
          fontSize: 12,
          padding: '5px 12px',
          borderRadius: 2,
          border: '1px solid var(--deck-line)',
          color: 'var(--deck-cyan-text)',
          textDecoration: 'none',
        }}
      >
        Open interactive graph →
      </Link>
    </section>
  )
}
