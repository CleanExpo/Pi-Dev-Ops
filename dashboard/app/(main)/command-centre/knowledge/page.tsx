// src/app/(founder)/founder/command-centre/knowledge/page.tsx
//
// Knowledge deck (UNI-2378 wave 1) — the wiki knowledge base and capability
// bus sections RELOCATED wholesale from the main command deck when it went
// calm-cockpit. Every tile renders exactly as it did on page.tsx; only the
// route moved. Deck register mirrors hermes-control-panel/page.tsx (fonts +
// styles.deck + shell tokens). Auth enforced by the (founder) layout.

export const dynamic = 'force-dynamic'

import Link from 'next/link'
import { Chakra_Petch, Syne, JetBrains_Mono } from 'next/font/google'
import { getToolCatalogue } from '@/lib/command-centre/tools/catalogue'
import { WikiGraphTile } from '@/components/command-centre/wiki-graph/WikiGraphTile'
import { IntentCatalogTile } from '@/components/command-centre/youtube-intent/IntentCatalogTile'
import { DeckDetails, DeckMoreLine, DECK_LIST_CAP } from '@/components/command-centre/DeckDetails'
import { DeckThemeShell } from '@/components/command-centre/DeckThemeShell'
import { railFor } from '@/components/command-centre/deck-visual-helpers'
import shell from '@/components/command-centre/shell.module.css'
import styles from '@/components/command-centre/command-deck.module.css'

const chakra = Chakra_Petch({
  weight: ['400', '500', '600', '700'],
  subsets: ['latin'],
  variable: '--font-chakra',
  display: 'swap',
})
const syne = Syne({
  weight: ['400', '500', '600', '700', '800'],
  subsets: ['latin'],
  variable: '--font-syne',
  display: 'swap',
})
const jbMono = JetBrains_Mono({
  weight: ['400', '500', '600'],
  subsets: ['latin'],
  variable: '--font-jbmono',
  display: 'swap',
})

export default async function KnowledgeDeckPage() {
  const tools = await getToolCatalogue()
  const sources = tools.reduce<Record<string, number>>((acc, t) => {
    acc[t.source] = (acc[t.source] ?? 0) + 1
    return acc
  }, {})

  return (
    <DeckThemeShell className={`${chakra.variable} ${syne.variable} ${jbMono.variable} ${styles.deck}`}>
      <Link href="/command-centre" className={styles.plink}>
        &larr; Command deck
      </Link>

      {/* ── Wiki knowledge base — canvas register (UNI-2339 slice 2) ── */}
      <div className={`${shell.canvasScope} ${shell.glassSectionHead}`} id="wiki-knowledge-base">
        <h2>Wiki Knowledge Base</h2>
        <span className={shell.glassSub}>button → queue → Mac runner → wiki-growth report</span>
        <div className={shell.glassHeadTools}>
          {/* WikiEnhanceControl deliberately omitted - KI-002. It POSTs to
              /api/command-centre/lanes/wiki/enhance, which enqueues a job into
              operator_jobs on a production database and requires a per-user
              identity this app does not have. The route is ABSENT rather than
              stubbed: an absent route cannot be silently filled in, a 501 stub is
              one line from live. */}
        </div>
      </div>

      {/* Wiki Graph (UNI-2304) — knowledge-base graph summary + link to full view. */}
      <section className={`${styles.reveal}`} style={{ animationDelay: '0.02s' }}>
        <WikiGraphTile />
      </section>

      <section className={`${styles.reveal}`} style={{ animationDelay: '0.03s' }}>
        <IntentCatalogTile />
      </section>

      {/* ── Capability bus — canvas register (UNI-2339 slice 2) ──────── */}
      <div className={`${shell.canvasScope} ${shell.glassSectionHead}`} id="capability-bus">
        <h2>Capability Bus</h2>
        <span className={shell.glassSub}>{tools.length} tools · {Object.keys(sources).length} sources</span>
      </div>

      <section className={`${styles.bus} ${styles.reveal}`} style={{ animationDelay: '0.04s' }}>
        <div className={styles.busTop}>
          <div className={styles.sources}>
            {Object.entries(sources).map(([source, count]) => (
              <span key={source} className={styles.sourceChip}>
                {source} <b>{count}</b>
              </span>
            ))}
          </div>
          <span className={styles.stamp}>
            <span className={styles.led} data-state="active" />
            List-only · no execution
          </span>
        </div>

        {/* Founder feedback 14/07/2026 — the raw tool_key dump collapses behind
            the shared DeckDetails disclosure (summary = counts already shown in
            the section head), capped with an honest "+N more". */}
        <DeckDetails
          title="Tool catalogue"
          stats={`${tools.length} tools · list-only`}
          testId="capability-bus-disclosure"
        >
          <div className={styles.toolGrid}>
            {tools.slice(0, DECK_LIST_CAP).map((tool) => (
              <div
                key={tool.tool_key}
                className={styles.toolRow}
                style={{ '--rail': railFor(tool.risk_class) } as React.CSSProperties}
              >
                <div style={{ minWidth: 0 }}>
                  <div className={styles.toolKey}>{tool.tool_key}</div>
                  <div className={styles.toolDesc}>{tool.description}</div>
                </div>
                <div style={{ flexShrink: 0, textAlign: 'right' }}>
                  <span className={styles.riskTag}>{tool.risk_class}</span>
                  {tool.approval_required && <span className={styles.approval}>approval</span>}
                </div>
              </div>
            ))}
          </div>
          <DeckMoreLine total={tools.length} shown={Math.min(tools.length, DECK_LIST_CAP)} />
        </DeckDetails>
      </section>
    </DeckThemeShell>
  )
}
