// UNI-1947 Pillar 3 — Brand × Source aggregator.
//
// Aggregates every per-brand/per-source adapter into a single 6×5 matrix the
// Empire Command Center renders without 30 client-side round-trips. Calls the
// five existing adapters via in-process HTTP fetch (same pattern as
// /api/empire/system-health) so we share one code path with the scanner cron.
//
// NO MOCK DATA — adapter failures surface as the adapter's own error response
// (status: 'err' with a real summary). Empty/unknown cells render honestly.
//
// Caching: a single in-memory 60s TTL covers the whole matrix (one object,
// not per-cell). `?force=1` busts the cache. `listBrands` is only called once
// per request so per-render dedupe (React `cache()`) is unnecessary on this
// React 18.2 baseline.

import { NextResponse } from 'next/server';
import { getAdminClient } from '@/lib/supabase/admin';
import { requireAdmin } from '@/lib/security/require-admin';
import type { BusinessSource, SourceKind } from '@/types/business-source';
import {
  getCache,
  setCache,
  type SourceMatrix,
  type SourceMatrixBrand,
} from './_helpers';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

const SOURCE_KINDS: SourceKind[] = ['github', 'linear', 'vercel', 'railway', 'supabase'];
const PORTFOLIO_SLUGS = [
  'synthex',
  'restoreassist',
  'disaster-recovery',
  'dr-nrpg',
  'carsi',
  'ccw-crm',
];
const TTL_MS = 60_000;
const ADAPTER_TIMEOUT_MS = 12_000;

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getBaseUrl(req: Request): string {
  try {
    const u = new URL(req.url);
    return `${u.protocol}//${u.host}`;
  } catch {
    /* fall through */
  }
  if (process.env.NEXT_PUBLIC_SITE_URL) return process.env.NEXT_PUBLIC_SITE_URL;
  if (process.env.VERCEL_URL) return `https://${process.env.VERCEL_URL}`;
  return 'http://localhost:3000';
}

function unreachable(source: SourceKind, msg: string): BusinessSource {
  return {
    source,
    status: 'err',
    summary: `${source} adapter unreachable`,
    last_update: null,
    error: msg.slice(0, 200),
  };
}

async function fetchCell(baseUrl: string, kind: SourceKind, slug: string): Promise<BusinessSource> {
  try {
    // Forward the service-role bearer so the (now-gated) adapter route admits
    // us — see require-admin.ts. This route runs server-side only and the key
    // never crosses the wire to the browser.
    const headers: Record<string, string> = { 'User-Agent': 'unite-group-source-matrix' };
    const svcKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
    if (svcKey) headers.authorization = `Bearer ${svcKey}`;
    const res = await fetch(`${baseUrl}/api/empire/sources/${kind}/${slug}`, {
      cache: 'no-store',
      signal: AbortSignal.timeout(ADAPTER_TIMEOUT_MS),
      headers,
    });
    if (!res.ok) {
      return unreachable(kind, `HTTP ${res.status}`);
    }
    const body = (await res.json()) as BusinessSource;
    // Defensive: an adapter must always include status — anything else is err.
    if (!body || typeof body.status !== 'string') {
      return unreachable(kind, 'invalid adapter response');
    }
    return body;
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return unreachable(kind, msg);
  }
}

// ─── Brand list ───────────────────────────────────────────────────────────────

interface BrandRow {
  slug: string;
  name: string;
}

async function listBrands(): Promise<BrandRow[]> {
  const supabase = getAdminClient();
  const { data, error } = await supabase
    .from('businesses')
    .select('slug, name, created_at, is_sandbox')
    .in('slug', PORTFOLIO_SLUGS)
    .not('is_sandbox', 'is', true)
    .order('created_at', { ascending: false });

  if (error || !data) {
    return [];
  }

  // Dedupe by slug — newest first wins.
  const seen = new Set<string>();
  const rows: BrandRow[] = [];
  for (const row of data) {
    const slug = row.slug as string | null;
    if (!slug || seen.has(slug)) continue;
    seen.add(slug);
    rows.push({ slug, name: (row.name as string) ?? slug });
  }
  // Stable canonical ordering matches PORTFOLIO_SLUGS.
  rows.sort((a, b) => PORTFOLIO_SLUGS.indexOf(a.slug) - PORTFOLIO_SLUGS.indexOf(b.slug));
  return rows;
}

// ─── Matrix builder ───────────────────────────────────────────────────────────

async function buildMatrix(baseUrl: string): Promise<SourceMatrix> {
  const brands = await listBrands();

  const brandResults = await Promise.all(
    brands.map(async (brand): Promise<SourceMatrixBrand> => {
      const cellEntries = await Promise.all(
        SOURCE_KINDS.map(async (kind) => {
          const cell = await fetchCell(baseUrl, kind, brand.slug);
          return [kind, cell] as const;
        }),
      );
      const cells = Object.fromEntries(cellEntries) as Record<SourceKind, BusinessSource>;
      return { slug: brand.slug, name: brand.name, cells };
    }),
  );

  return {
    computed_at: new Date().toISOString(),
    brands: brandResults,
  };
}

// ─── Handler ──────────────────────────────────────────────────────────────────

export async function GET(req: Request) {
  const gate = await requireAdmin(req);
  if (gate instanceof NextResponse) return gate;
  const url = new URL(req.url);
  const force = url.searchParams.get('force') === '1';

  const now = Date.now();
  const cached = getCache();
  if (!force && cached && now - cached.computed_at < TTL_MS) {
    return NextResponse.json(cached.payload, {
      headers: {
        'Cache-Control': 'no-store',
        'X-Source-Matrix-Cache': 'hit',
      },
    });
  }

  const baseUrl = getBaseUrl(req);
  const payload = await buildMatrix(baseUrl);

  setCache({ computed_at: now, payload });

  return NextResponse.json(payload, {
    headers: {
      'Cache-Control': 'no-store',
      'X-Source-Matrix-Cache': force ? 'force' : 'miss',
    },
  });
}
