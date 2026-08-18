// src/app/(founder)/founder/command-centre/wiki-graph/page.tsx
//
// Wiki Graph View (UNI-2304) — an Obsidian-style interactive force-directed
// graph of the founder wiki knowledge base, inside the command centre.
// Auth-gated; queries wiki_pages directly server-side and builds the graph via
// the shared pure builder (same logic the /api/command-centre/wiki-graph route
// exposes for the deck tile). Honest empty state when the wiki is unsynced.

export const dynamic = 'force-dynamic'

import Link from 'next/link'
// Data access REBUILT for this app, not ported. The source's
// `@/lib/supabase/server` is an anon-key, RLS-enforced, per-user client; the same
// specifier resolves here to a service-role client and this app has no per-user
// identity. Auth is enforced upstream by proxy.ts, so there is no getUser() to call.
//
// Client is scoped to the Unite-Group production Supabase project
// (lksfwktwtmyznckodsau), where wiki_pages actually lives — NOT this app's
// Pi-CEO-scoped lib/supabase/server.ts client, which points at a different project
// (zbryrmxmgfmslqzizsto) that has no wiki_pages table. See
// lib/supabase/unite-group-server.ts and the matching note in the API route this
// page's tile shares logic with (app/api/command-centre/wiki-graph/route.ts).
import { createUniteGroupServerClient } from '@/lib/supabase/unite-group-server'
import { buildWikiGraph, type WikiPageRow } from '@/lib/command-centre/wiki-graph'
import { WikiGraphCanvas } from '@/components/command-centre/wiki-graph/WikiGraphCanvas'

// PostgREST's default row cap — made explicit so truncation can be surfaced
// honestly instead of silently rendering a partial graph as complete.
const WIKI_PAGES_LIMIT = 1000

function formatSync(iso: string | null): string {
  if (!iso) return 'never'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return 'unknown'
  return d.toLocaleString('en-AU', {
    timeZone: 'Australia/Brisbane',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default async function WikiGraphPage() {
  // createUniteGroupServerClient() THROWS when the Unite-Group Supabase vars are unset,
  // and it used to be called bare, outside any try. So `error` below could only ever hold
  // a PostgREST query error — a missing-config error bypassed it entirely, both EmptyState
  // branches were unreachable, and the throw surfaced as the generic Application Error
  // panel with a redacted message and an opaque digest. Five authenticated users hit that
  // between 2026-08-09 and 2026-08-14; the vars are still absent from the Vercel project.
  // The header's promise of an "honest empty state" was false for the one failure mode
  // actually happening.
  //
  // The factory's throw is deliberate and stays — it is pinned by a test that stops it
  // falling back to the Pi-CEO client, which is the wrong Supabase project (#634). The
  // call site is what needed to handle it.
  let error: unknown = null
  let rows: WikiPageRow[] = []
  try {
    const supabase = createUniteGroupServerClient()
    const res = await supabase
      .from('wiki_pages')
      .select('id, title, tags, content, updated_at')
      .limit(WIKI_PAGES_LIMIT)
    error = res.error
    rows = (res.data ?? []) as WikiPageRow[]
  } catch (e) {
    // Logged server-side only. The existing EmptyState copy is accurate and secret-free;
    // the caught message names env vars, so it must never reach the page.
    console.error('[wiki-graph page] unhandled failure building graph:', e)
    error = e
  }

  const graph = error ? null : buildWikiGraph(rows)
  const truncated = !error && rows.length === WIKI_PAGES_LIMIT

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        background: '#fffdf7',
        color: '#14241b',
        padding: '1.25rem 1.5rem',
        gap: '1rem',
        fontFamily: 'var(--font-chakra), var(--font-geist-sans), system-ui, sans-serif',
      }}
    >
      <header style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', justifyContent: 'space-between', gap: '0.75rem' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Link href="/command-centre" style={{ fontSize: 11, color: 'rgba(21,128,61,0.7)', textDecoration: 'none' }}>
            &larr; Command Deck
          </Link>
          <h1 style={{ fontSize: '1.4rem', fontWeight: 600, letterSpacing: '-0.01em', color: '#15803d', margin: 0 }}>
            Wiki Graph
          </h1>
          {truncated && (
            <span style={{ fontSize: 11, color: '#b45309' }}>
              showing first {WIKI_PAGES_LIMIT} pages
            </span>
          )}
        </div>
        <div style={{ display: 'flex', gap: '1.25rem', fontSize: 12, color: '#5a6b62' }}>
          <span>
            <b style={{ color: '#14241b' }}>{graph?.pageCount ?? 0}</b> pages
          </span>
          <span>
            <b style={{ color: '#14241b' }}>{graph?.edges.length ?? 0}</b> links
          </span>
          <span>
            synced <b style={{ color: '#14241b' }}>{formatSync(graph?.lastSync ?? null)}</b>
          </span>
        </div>
      </header>

      {error ? (
        <EmptyState
          title="Wiki graph unavailable"
          detail="Could not read the wiki knowledge base. The wiki_pages source did not respond."
        />
      ) : !graph || graph.pageCount === 0 ? (
        <EmptyState
          title="Wiki not synced"
          detail="0 pages found in the knowledge base. Once the Obsidian 2nd Brain sync populates wiki_pages, the graph will render here."
        />
      ) : (
        <div style={{ flex: 1, minHeight: 0, position: 'relative' }}>
          <WikiGraphCanvas nodes={graph.nodes} edges={graph.edges} />
          <p style={{ margin: '0.5rem 0 0', fontSize: 11, color: '#5a6b62' }}>
            {/* "· click to open the page" removed with the click handler — KI-005. A
                caption is part of the surface's claim about itself; leaving it would
                advertise an interaction that no longer exists, which is the same
                misrepresentation the click was removed to avoid. */}
            Drag to pan · scroll to zoom · drag a node to move it · hover to highlight neighbours
          </p>
        </div>
      )}
    </div>
  )
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div
      style={{
        flex: 1,
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        textAlign: 'center',
        gap: 8,
        borderRadius: 2,
        border: '1px solid rgba(45,187,87,0.20)',
        background: '#ffffff',
      }}
    >
      <span style={{ fontSize: 14, fontWeight: 600, color: '#15803d' }}>{title}</span>
      <span style={{ fontSize: 12, color: '#5a6b62', maxWidth: 420 }}>{detail}</span>
    </div>
  )
}
