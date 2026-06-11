'use client';

// Business360Grid — Zone 4 of /command-center.
//
// Six portfolio brand tiles (per [[command-center-redesign-proposal-2026-05-14]]
// Zone 4 spec): CCW · RestoreAssist · DR · NRPG · CARSI · Synthex. Unite-Group
// itself sits in Zone 1 (the wordmark) so it's intentionally excluded.
//
// Layout:
//   - 1-col on narrow viewports, 2-col on lg+
//   - 1px grid gap (Candy-Red-on-near-black ground bleeds through, matches
//     the KpiStrip pattern)
//   - Section label up top, hush-ink, mono caps

import { BusinessTile } from './BusinessTile';
import { BUSINESS_360_TILES, type Business360Datum } from './business-360-data';
import { SourceBadge } from '../SourceBadge';

export interface Business360GridProps {
  /** Override tiles — used by the server-rendered page for live wiring. */
  tiles?: Business360Datum[];
  /**
   * When set, the SourceBadge flips from `seed` to `live`. Comes from the
   * server-rendered page after reading pi_ceo_health_snapshots.
   */
  sourceLiveAt?: string;
}

interface Business360GridInternalProps extends Business360GridProps {
  /**
   * Active route locale, threaded from CommandCenterShell so tile hrefs
   * preserve the founder's locale. Falls back to 'en' for unit tests.
   */
  locale?: string;
}

export function Business360Grid({
  tiles = BUSINESS_360_TILES,
  sourceLiveAt,
  locale = 'en',
}: Business360GridInternalProps = {}) {
  const isLive = !!sourceLiveAt;
  return (
    <section
      className="flex flex-col"
      style={{ background: 'var(--cc-bg-soft)' }}
      aria-label="Business 360"
    >
      <header
        className="flex items-center justify-between px-5 h-10"
        style={{
          background: 'var(--cc-bg)',
          borderBottom: '1px solid var(--cc-grid)',
        }}
      >
        <span
          className="font-mono text-[11px] uppercase tracking-[0.22em]"
          style={{ color: 'var(--cc-ink-dim)' }}
        >
          Zone 4 · Business 360
        </span>
        <span className="flex items-center gap-3">
          <span
            className="font-mono text-[10px] uppercase tracking-[0.18em]"
            style={{ color: 'var(--cc-ink-hush)' }}
          >
            {tiles.length} portfolio brands
          </span>
          {isLive ? (
            <SourceBadge
              mode="live"
              label="health_snapshots · 90d"
              lastUpdatedAt={sourceLiveAt}
            />
          ) : (
            <SourceBadge mode="seed" label="static · awaits financial_records aggregate" />
          )}
        </span>
      </header>

      <div
        className="grid grid-cols-1 lg:grid-cols-2"
        style={{ gap: '1px', background: 'var(--cc-grid)' }}
      >
        {tiles.map((b) => (
          <BusinessTile key={b.id} data={b} locale={locale} />
        ))}
      </div>
    </section>
  );
}
