export const dynamic = 'force-dynamic'

import Link from 'next/link'
import path from 'node:path'
import { promises as fs } from 'node:fs'
import { DeckThemeShell } from '@/components/command-centre/DeckThemeShell'

type IntentApiResponse = {
  updatedAt: string | null
  acceptedCount: number
  excludedCount: number
  topAccepted: Array<{
    video_key: string
    title?: string
    channel?: string
    watch_count_window?: number
    strategic_hits?: string[]
  }>
  topics: Array<{ topic: string; frequency_score: number; confidence: number }>
  personaTraits: Array<{ trait: string; confidence: number }>
  verticalPathways: Array<{ vertical_id: string; direction_theme: string; strategic_priority: number }>
  wikiPages: string[]
  boardUrl: string
}

async function fetchIntentData(): Promise<IntentApiResponse> {
  const statePath = path.join(process.cwd(), '.harness', 'ugn_intent_youtube', 'state.json')
  const raw = await fs.readFile(statePath, 'utf-8')
  const parsed = JSON.parse(raw) as {
    updated_at?: string
    videos?: IntentApiResponse['topAccepted']
    topics?: IntentApiResponse['topics']
    persona_traits?: IntentApiResponse['personaTraits']
    vertical_pathway_signals?: IntentApiResponse['verticalPathways']
    wiki_pages?: string[]
  }
  const videos = parsed.videos ?? []
  const accepted = videos.filter((v) => (v as { status?: string }).status === 'accepted')
  const excluded = videos.filter((v) => (v as { status?: string }).status === 'excluded')
  return {
    updatedAt: parsed.updated_at ?? null,
    acceptedCount: accepted.length,
    excludedCount: excluded.length,
    topAccepted: accepted.sort((a, b) => (b.watch_count_window ?? 1) - (a.watch_count_window ?? 1)).slice(0, 10),
    topics: parsed.topics ?? [],
    personaTraits: parsed.persona_traits ?? [],
    verticalPathways: parsed.vertical_pathway_signals ?? [],
    wikiPages: parsed.wiki_pages ?? [],
    boardUrl: 'http://localhost:7119',
  }
}

export default async function YouTubeIntentPage() {
  let data: IntentApiResponse | null = null
  let error: string | null = null
  try {
    data = await fetchIntentData()
  } catch (e) {
    error = e instanceof Error ? e.message : 'load failed'
  }

  return (
    <DeckThemeShell className="">
      <Link href="/command-centre/knowledge" style={{ fontSize: 12, textDecoration: 'none' }}>
        &larr; Knowledge deck
      </Link>
      <h1 style={{ margin: 0, fontSize: 24, color: 'var(--deck-text)' }}>UG-N Intent-Only YouTube Catalog</h1>
      {error || !data ? (
        <p style={{ color: 'var(--deck-abort-text)', marginTop: 12 }}>Could not load catalog: {error}</p>
      ) : (
        <div style={{ display: 'grid', gap: 16 }}>
          <section>
            <p style={{ margin: 0, color: 'var(--deck-muted)' }}>
              Updated: <b style={{ color: 'var(--deck-text)' }}>{data.updatedAt ?? 'never'}</b>
            </p>
            <p style={{ margin: '6px 0 0', color: 'var(--deck-muted)' }}>
              Accepted strategic signals: <b style={{ color: 'var(--deck-text)' }}>{data.acceptedCount}</b> · Excluded:{' '}
              <b style={{ color: 'var(--deck-text)' }}>{data.excludedCount}</b>
            </p>
            <a href={data.boardUrl} target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>
              Open live Excalidraw board ({data.boardUrl})
            </a>
          </section>

          <section>
            <h2 style={{ margin: 0, fontSize: 16 }}>Most watched strategic selections</h2>
            <ul>
              {data.topAccepted.map((item) => (
                <li key={item.video_key}>
                  <b>{item.title ?? item.video_key}</b> ({item.channel ?? 'unknown channel'}) · watched{' '}
                  {item.watch_count_window ?? 1} times · topics: {(item.strategic_hits ?? []).join(', ') || 'none'}
                </li>
              ))}
            </ul>
          </section>

          <section>
            <h2 style={{ margin: 0, fontSize: 16 }}>Persona traits</h2>
            <ul>
              {data.personaTraits.map((trait, idx) => (
                <li key={`${trait.trait}-${idx}`}>
                  {trait.trait} (confidence {trait.confidence})
                </li>
              ))}
            </ul>
          </section>

          <section>
            <h2 style={{ margin: 0, fontSize: 16 }}>Vertical pathway signals</h2>
            <ul>
              {data.verticalPathways.map((pathway, idx) => (
                <li key={`${pathway.vertical_id}-${idx}`}>
                  <b>{pathway.vertical_id}</b>: {pathway.direction_theme} (priority {pathway.strategic_priority})
                </li>
              ))}
            </ul>
          </section>

          <section>
            <h2 style={{ margin: 0, fontSize: 16 }}>Wiki pages (2nd brain)</h2>
            <ul>
              {data.wikiPages.map((page) => (
                <li key={page}>
                  <code>{page}</code>
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </DeckThemeShell>
  )
}
