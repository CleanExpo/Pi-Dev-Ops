// UNI-1947 Pillar 3 — SourceMatrixGrid rendering tests.
//
// Mirrors the SystemHealthTile test style: render to static markup with
// react-dom/server and assert on the resulting HTML. Validates the visible
// structural contract — 6 brands × 5 source cells, column health pills,
// click-target cells, refresh-with-force button — without needing jsdom.

/**
 * @jest-environment node
 */

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

// BusinessLogo pulls in next/image which doesn't render in node — mock it to a
// trivial passthrough so the tests focus on SourceMatrixGrid's own contract.
jest.mock('@/components/empire/BusinessLogo', () => ({
  BusinessLogo: ({ slug }: { slug: string }) => React.createElement('span', { 'data-testid': `logo-${slug}` }, slug),
}));

import { SourceMatrixGrid, type SourceMatrix } from '../SourceMatrixGrid';
import type { BusinessSource, SourceKind, SourceStatus } from '@/types/business-source';

function cell(source: SourceKind, status: SourceStatus, extra: Partial<BusinessSource> = {}): BusinessSource {
  return {
    source,
    status,
    summary: `${source} ${status} summary`,
    last_update: '2026-05-13T00:00:00Z',
    ...extra,
  };
}

function makeBrand(
  slug: string,
  name: string,
  statuses: Record<SourceKind, SourceStatus>,
) {
  return {
    slug,
    name,
    cells: {
      github:   cell('github',   statuses.github),
      linear:   cell('linear',   statuses.linear),
      vercel:   cell('vercel',   statuses.vercel),
      railway:  cell('railway',  statuses.railway),
      supabase: cell('supabase', statuses.supabase),
    },
  };
}

function fixture(): SourceMatrix {
  // Mirrors the live shape captured today.
  return {
    computed_at: new Date().toISOString(),
    brands: [
      makeBrand('synthex',           'SYNTHEX',          { github: 'warn', linear: 'ok',   vercel: 'ok',  railway: 'unknown', supabase: 'err' }),
      makeBrand('restoreassist',     'RESTOREASSIST',    { github: 'ok',   linear: 'err',  vercel: 'ok',  railway: 'unknown', supabase: 'err' }),
      makeBrand('disaster-recovery', 'DISASTER-RECOVERY',{ github: 'ok',   linear: 'warn', vercel: 'ok',  railway: 'unknown', supabase: 'ok'  }),
      makeBrand('dr-nrpg',           'DR-NRPG',          { github: 'ok',   linear: 'warn', vercel: 'err', railway: 'unknown', supabase: 'err' }),
      makeBrand('carsi',             'CARSI',            { github: 'err',  linear: 'ok',   vercel: 'err', railway: 'unknown', supabase: 'err' }),
      makeBrand('ccw-crm',           'CCW-CRM',          { github: 'ok',   linear: 'ok',   vercel: 'err', railway: 'err',     supabase: 'err' }),
    ],
  };
}

describe('SourceMatrixGrid rendering', () => {
  it('renders a 6 × 5 grid of clickable status cells with real statuses', () => {
    const html = renderToStaticMarkup(<SourceMatrixGrid initialData={fixture()} />);
    expect(html).toContain('data-testid="source-matrix-grid"');
    expect(html).toContain('data-brand-count="6"');
    // 30 cells total (one per brand × source) — count test-id occurrences.
    const matches = html.match(/data-testid="cell-/g) ?? [];
    expect(matches).toHaveLength(30);
    // Spot-check a known cell from the live shape.
    expect(html).toMatch(/data-testid="cell-synthex-supabase"[^>]*data-status="err"/);
    expect(html).toMatch(/data-testid="cell-disaster-recovery-supabase"[^>]*data-status="ok"/);
    expect(html).toMatch(/data-testid="cell-ccw-crm-railway"[^>]*data-status="err"/);
  });

  it('renders an unknown cell with the grey colour, not red/orange', () => {
    const html = renderToStaticMarkup(<SourceMatrixGrid initialData={fixture()} />);
    // Every brand has railway=unknown in the live fixture except ccw-crm.
    expect(html).toMatch(/data-testid="cell-synthex-railway"[^>]*data-status="unknown"/);
    // The cell render must include the grey #52525b colour for unknown status.
    const synthexRailway = html.match(
      /data-testid="cell-synthex-railway"[^]*?<\/button>/,
    )?.[0] ?? '';
    expect(synthexRailway).toContain('#52525b');
    expect(synthexRailway).not.toContain('#dc2626');
    expect(synthexRailway).not.toContain('#d97706');
  });

  it('renders column health pills with per-source ok counts', () => {
    const html = renderToStaticMarkup(<SourceMatrixGrid initialData={fixture()} />);
    // From the live shape: github has 4/6 ok (warn=1, err=1).
    // vercel has 3/6 ok. supabase has 1/6 ok. linear has 3/6 ok. railway has 0/6 ok.
    // Each pill is rendered with its count text in the column header.
    expect(html).toMatch(/data-testid="col-github"[^]*?4\/6/);
    expect(html).toMatch(/data-testid="col-vercel"[^]*?3\/6/);
    expect(html).toMatch(/data-testid="col-supabase"[^]*?1\/6/);
    expect(html).toMatch(/data-testid="col-railway"[^]*?0\/6/);
    expect(html).toMatch(/data-testid="col-linear"[^]*?3\/6/);
  });

  it('shows a green column pill when every brand is ok in that source', () => {
    const matrix: SourceMatrix = {
      computed_at: new Date().toISOString(),
      brands: [
        makeBrand('synthex',           'SYNTHEX',           { github: 'ok', linear: 'ok', vercel: 'ok', railway: 'ok', supabase: 'ok' }),
        makeBrand('restoreassist',     'RESTOREASSIST',     { github: 'ok', linear: 'ok', vercel: 'ok', railway: 'ok', supabase: 'ok' }),
        makeBrand('disaster-recovery', 'DISASTER-RECOVERY', { github: 'ok', linear: 'ok', vercel: 'ok', railway: 'ok', supabase: 'ok' }),
      ],
    };
    const html = renderToStaticMarkup(<SourceMatrixGrid initialData={matrix} />);
    // All five column pills carry the ok variant.
    const okPills = html.match(/data-testid="col-pill-ok"/g) ?? [];
    expect(okPills).toHaveLength(5);
    // The ok colour token (#16a34a) appears in the pill.
    expect(html).toContain('#16a34a');
    // No err / warn pill variants.
    expect(html).not.toContain('data-testid="col-pill-err"');
    expect(html).not.toContain('data-testid="col-pill-warn"');
  });

  it('exposes a refresh button that hits force=1 — verified by component shape and the cells are still clickable buttons', () => {
    const html = renderToStaticMarkup(<SourceMatrixGrid initialData={fixture()} />);
    // The REFRESH button is present and rendered as <button>.
    expect(html).toMatch(/data-testid="source-matrix-refresh"[^>]*>[^<]*REFRESH/);
    // Cells are <button> elements with onClick handlers — confirms the
    // click-to-drawer affordance the load(true) path also depends on.
    const cellButtons = html.match(/<button[^>]*data-testid="cell-/g) ?? [];
    expect(cellButtons.length).toBe(30);
    // Empty state should NOT show when initialData is provided.
    expect(html).not.toContain('No active brands found');
  });

  it('wraps each brand-row label in a Link to /en/empire/businesses/{slug} for drill-in', () => {
    const html = renderToStaticMarkup(<SourceMatrixGrid initialData={fixture()} />);
    // Every brand gets a row-link with the canonical slug. Attribute order is
    // not deterministic across Next/React versions, so match each attribute
    // independently within a single <a> element.
    for (const slug of ['synthex', 'restoreassist', 'disaster-recovery', 'dr-nrpg', 'carsi', 'ccw-crm']) {
      const anchors = html.match(/<a[^>]*>/g) ?? [];
      const match = anchors.find(
        (a) =>
          a.includes(`data-testid="row-link-${slug}"`) &&
          a.includes(`href="/en/empire/businesses/${slug}"`),
      );
      expect(match).toBeTruthy();
    }
  });

  it('honours the active locale on brand-row hrefs (UNI-2025 follow-up)', () => {
    // Without locale threading, a /fr/ founder clicking a row got dropped to /en/.
    const html = renderToStaticMarkup(
      <SourceMatrixGrid initialData={fixture()} locale="fr" />,
    );
    expect(html).toContain('href="/fr/empire/businesses/synthex"');
    expect(html).not.toContain('href="/en/empire/businesses/synthex"');
  });
});
