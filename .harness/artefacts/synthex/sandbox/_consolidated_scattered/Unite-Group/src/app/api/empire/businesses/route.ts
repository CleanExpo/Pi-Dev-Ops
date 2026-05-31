import { NextRequest, NextResponse } from 'next/server';
import { getAdminClient } from '@/lib/supabase/admin';
import { requireAdmin } from '@/lib/security/require-admin';

export const dynamic = 'force-dynamic';

// UNI-1947 Pillar 2: FALLBACK_BUSINESSES const removed. The API now returns
// whatever is in the `businesses` table (filtered to the canonical portfolio
// slugs and deduped). When the table is empty or the query fails, we return
// `businesses: []` with `has_live_data: false` — the UI shows an
// EmptyState rather than fabricated rows.
//
// TODO(Pillar 3 / Task 3.2): replace this inline slug list with
// `.eq('is_sandbox', false)` once the businesses.is_sandbox migration lands.
const PORTFOLIO_SLUGS = [
  'synthex',
  'restoreassist',
  'dr-nrpg',
  'carsi',
  'ccw-crm',
  'disaster-recovery',
];

export type BusinessHealthRow = {
  id: string;
  name: string;
  status: string;
  arr_aud: number;
  overall_health: number | null;
  security_score: number | null;
  dependencies: number | null;
  security_findings: number | null;
  snapshot_at: string | null;
};

function healthToStatus(score: number): string {
  if (score >= 80) return 'operational';
  if (score >= 60) return 'building';
  if (score >= 40) return 'degraded';
  return 'down';
}

export async function GET(req: NextRequest) {
  const gate = await requireAdmin(req);
  if (gate instanceof NextResponse) return gate;
  const supabase = getAdminClient();

  // Latest snapshot per project_id
  const { data: snapshots, error: snapshotError } = await supabase
    .from('pi_ceo_health_snapshots')
    .select('project_id, overall_health, security_score, dependencies, security_findings, snapshot_at')
    .order('snapshot_at', { ascending: false });

  if (snapshotError) {
    console.error('[empire/businesses] snapshot query error:', snapshotError.message);
  }

  const latestByProject = new Map<string, {
    project_id: string;
    overall_health: number | null;
    security_score: number | null;
    dependencies: number | null;
    security_findings: number | null;
    snapshot_at: string | null;
  }>();
  for (const row of (snapshots ?? [])) {
    if (!latestByProject.has(row.project_id)) {
      latestByProject.set(row.project_id, row);
    }
  }

  // Restrict to canonical portfolio slugs; order newest-first so the
  // dedupe-by-slug below keeps the freshest row when twin seed rows exist.
  // Pillar 3: filter sandbox rows at the query level. `is_sandbox IS NOT TRUE`
  // matches both FALSE and NULL — the column lands NOT NULL DEFAULT FALSE via
  // migration 20260513170300, but `IS NOT TRUE` keeps the query safe against
  // any legacy rows inserted before the migration ran.
  const { data: bizRowsRaw, error: bizError } = await supabase
    .from('businesses')
    .select('id, slug, name, status, arr_aud, pi_ceo_key, created_at, is_sandbox')
    .in('slug', PORTFOLIO_SLUGS)
    .not('is_sandbox', 'is', true)
    .order('created_at', { ascending: false });

  if (bizError) {
    console.error('[empire/businesses] businesses query error:', bizError.message);
  }

  // Dedupe by slug — first occurrence wins (newest row given the order above).
  const seenSlugs = new Set<string>();
  const bizRows = (bizRowsRaw ?? []).filter(row => {
    const slug = row.slug as string | null;
    if (!slug || seenSlugs.has(slug)) return false;
    seenSlugs.add(slug);
    return true;
  });

  const results: BusinessHealthRow[] = bizRows.map(biz => {
    const piKey = biz.pi_ceo_key ?? biz.slug ?? biz.id;
    const snap = latestByProject.get(piKey) ?? latestByProject.get(biz.id);
    const overallHealth = snap?.overall_health ?? null;

    return {
      id: biz.slug ?? biz.pi_ceo_key ?? biz.id,
      name: biz.name,
      status: overallHealth !== null ? healthToStatus(overallHealth) : (biz.status ?? 'unknown'),
      arr_aud: biz.arr_aud ?? 0,
      overall_health: overallHealth,
      security_score: snap?.security_score ?? null,
      dependencies: snap?.dependencies ?? null,
      security_findings: snap?.security_findings ?? null,
      snapshot_at: snap?.snapshot_at ?? null,
    };
  });

  const totalArr = results.reduce((s, b) => s + (b.arr_aud ?? 0), 0);
  const scoredBizs = results.filter(b => b.overall_health !== null);
  const avgHealth = scoredBizs.length > 0
    ? Math.round(scoredBizs.reduce((s, b) => s + (b.overall_health ?? 0), 0) / scoredBizs.length)
    : null;
  const atRisk = results.filter(b => b.overall_health !== null && b.overall_health < 60).length;
  const lastRescan = results
    .map(b => b.snapshot_at)
    .filter(Boolean)
    .sort()
    .at(-1) ?? null;

  return NextResponse.json(
    {
      businesses: results,
      summary: {
        total_arr: totalArr,
        avg_health: avgHealth,
        at_risk_count: atRisk,
        last_rescan: lastRescan,
        has_live_data: snapshots !== null && (snapshots?.length ?? 0) > 0,
      },
      fetched_at: new Date().toISOString(),
    },
    { headers: { 'Cache-Control': 'no-store' } }
  );
}
