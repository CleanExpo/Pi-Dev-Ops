// Empire → Businesses index.
//
// Lists the canonical six portfolio brands (PORTFOLIO_SLUGS from the
// /api/empire/businesses + /api/empire/source-matrix registry). Each card
// drills into /[locale]/empire/businesses/[slug].
//
// Fix for the System Health → Businesses 404 — the drillHref pointed at
// /en/empire/businesses but only [slug]/page.tsx existed.

import Link from 'next/link';
import { BusinessLogo } from '@/components/empire/BusinessLogo';
import { PortfolioTile } from '@/components/empire/PortfolioTile';

// Canonical slugs — must stay in sync with PORTFOLIO_SLUGS in
// src/app/api/empire/businesses/route.ts and source-matrix/route.ts.
const PORTFOLIO_BRANDS: { slug: string; name: string; team: string }[] = [
  { slug: 'synthex',           name: 'Synthex',       team: 'SYN'   },
  { slug: 'restoreassist',     name: 'RestoreAssist', team: 'RA'    },
  { slug: 'disaster-recovery', name: 'DR Platform',   team: 'DR'    },
  { slug: 'dr-nrpg',           name: 'NRPG',          team: 'NRPG'  },
  { slug: 'carsi',             name: 'CARSI',         team: 'CARSI' },
  { slug: 'ccw-crm',           name: 'CCW-CRM',       team: 'CCW'   },
];

export const metadata = {
  title: 'Businesses · Empire Command Center',
};

export default async function EmpireBusinessesIndex({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return (
    <div
      style={{
        minHeight: '100vh',
        background: 'var(--canvas)',
        color: 'var(--ink-primary)',
        fontFamily: 'system-ui, sans-serif',
      }}
    >
      {/* Header */}
      <header
        style={{
          borderBottom: '1px solid var(--border-hairline)',
          padding: '14px 32px',
          background: 'var(--surface-1)',
          display: 'flex',
          alignItems: 'center',
          gap: 16,
        }}
      >
        <Link
          href={`/${locale}/empire`}
          style={{
            fontSize: 12,
            fontWeight: 600,
            fontFamily: 'var(--font-mono)',
            color: 'var(--ink-tertiary)',
            textDecoration: 'none',
            letterSpacing: '0.04em',
          }}
        >
          ← Command Center
        </Link>
        <div style={{ width: 1, height: 24, background: 'var(--border-hairline)' }} />
        <div>
          <div style={{ fontSize: 15, fontWeight: 600, letterSpacing: '-0.3px' }}>
            Businesses
          </div>
          <div style={{ fontSize: 11, color: 'var(--ink-tertiary)', marginTop: 1 }}>
            Six portfolio brands · click a card to drill in
          </div>
        </div>
      </header>

      <main style={{ padding: '24px 32px', maxWidth: 1280, margin: '0 auto' }}>
        <div
          style={{
            fontSize: 10,
            fontWeight: 700,
            fontFamily: 'var(--font-mono)',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: 'var(--ink-tertiary)',
            marginBottom: 12,
          }}
        >
          Portfolio · {PORTFOLIO_BRANDS.length} brands
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
            gap: 12,
          }}
        >
          {PORTFOLIO_BRANDS.map((brand) => (
            <Link
              key={brand.slug}
              href={`/${locale}/empire/businesses/${brand.slug}`}
              data-testid={`brand-card-${brand.slug}`}
              style={{ textDecoration: 'none', color: 'inherit' }}
            >
              <PortfolioTile
                title={brand.name}
                description="Click to drill in"
                status="operational"
                brandSlug={brand.slug}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <BusinessLogo slug={brand.slug} size="md" />
                  <div
                    style={{
                      fontSize: 10,
                      fontFamily: 'var(--font-mono)',
                      color: 'var(--ink-tertiary)',
                    }}
                  >
                    {brand.slug}
                  </div>
                </div>

                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginTop: 12,
                    paddingTop: 10,
                    borderTop: '1px solid var(--border-hairline)',
                  }}
                >
                  <span
                    style={{
                      fontSize: 10,
                      fontFamily: 'var(--font-mono)',
                      letterSpacing: '0.08em',
                      textTransform: 'uppercase',
                      color: 'var(--ink-tertiary)',
                    }}
                  >
                    Linear team
                  </span>
                  <span
                    style={{
                      fontSize: 11,
                      fontFamily: 'var(--font-mono)',
                      fontWeight: 700,
                      color: 'var(--ink-secondary)',
                    }}
                  >
                    {brand.team}
                  </span>
                </div>

                <span
                  style={{
                    display: 'inline-block',
                    marginTop: 12,
                    fontSize: 11,
                    fontFamily: 'var(--font-mono)',
                    fontWeight: 600,
                    color: 'var(--ink-primary)',
                    letterSpacing: '0.04em',
                  }}
                >
                  Open detail →
                </span>
              </PortfolioTile>
            </Link>
          ))}
        </div>
      </main>
    </div>
  );
}
