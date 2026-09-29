export const dynamic = 'force-dynamic'

import Link from 'next/link'
import { DeckThemeShell } from '@/components/command-centre/DeckThemeShell'
import { INTENT_ABSENT_MESSAGE, loadIntentState } from '@/lib/command-centre/youtube-intent-state'

export default async function YouTubeIntentPage() {
  const load = await loadIntentState()
  const data = load.kind === 'ok' ? load.summary : null
  // Absent is the normal state on a deployed host: say so plainly, without a server path.
  const notice = load.kind === 'absent' ? INTENT_ABSENT_MESSAGE : load.kind === 'error' ? load.message : null

  return (
    <DeckThemeShell className="">
      <Link href="/command-centre/knowledge" style={{ fontSize: 12, textDecoration: 'none' }}>
        &larr; Knowledge deck
      </Link>
      <h1 style={{ margin: 0, fontSize: 24, color: 'var(--deck-text)' }}>UG-N Intent-Only YouTube Catalog</h1>
      {!data ? (
        <p
          style={{ color: load.kind === 'absent' ? 'var(--deck-muted)' : 'var(--deck-abort-text)', marginTop: 12 }}
          data-mc-empty={load.kind === 'absent' ? 'the intent catalogue is built on the mesh machine and is not deployed to this host' : undefined}
        >
          {notice}
        </p>
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
            {data.boardUrl ? (
              <a href={data.boardUrl} target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>
                Open live Excalidraw board ({data.boardUrl})
              </a>
            ) : null}
          </section>

          <section>
            <h2 style={{ margin: 0, fontSize: 16 }}>Most watched strategic selections</h2>
            <ul>
              {data.topAccepted.map((item) => (
                <li key={item.video_key} data-mc-data="intent-signal">
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
