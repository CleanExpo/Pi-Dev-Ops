// Server-only helper that reads the same portfolio summary the
// /api/empire/businesses route returns, but bypasses the requireAdmin
// gate because the calling server components have already authenticated
// the founder via checkAdminSession. Keeps the auth boundary at the page,
// not the data layer.

import { getAdminClient } from '@/lib/supabase/admin';

const PORTFOLIO_SLUGS = [
  'synthex',
  'restoreassist',
  'dr-nrpg',
  'carsi',
  'ccw-crm',
  'disaster-recovery',
];

export interface PortfolioSummary {
  /** AUD cents summed across all non-sandbox portfolio businesses. */
  total_arr_cents: number;
  /** Count of businesses with overall_health < 60. */
  at_risk_count: number;
  /** ISO timestamp of the newest snapshot across the portfolio. */
  last_rescan: string | null;
  /** True when at least one health snapshot exists. */
  has_live_data: boolean;
  /** ISO timestamp the read completed — used as SourceBadge lastUpdatedAt. */
  fetched_at: string;
}

export async function readPortfolioSummary(): Promise<PortfolioSummary | null> {
  try {
    const supabase = getAdminClient();
    const [snapshotsRes, bizRes] = await Promise.all([
      supabase
        .from('pi_ceo_health_snapshots')
        .select('project_id, overall_health, snapshot_at')
        .order('snapshot_at', { ascending: false }),
      supabase
        .from('businesses')
        .select('id, slug, pi_ceo_key, arr_aud, is_sandbox')
        .in('slug', PORTFOLIO_SLUGS)
        .not('is_sandbox', 'is', true)
        .order('created_at', { ascending: false }),
    ]);

    const snapshots = snapshotsRes.data ?? [];
    const bizRowsRaw = bizRes.data ?? [];

    // Dedupe businesses by slug — first occurrence wins (newest row).
    const seen = new Set<string>();
    const bizRows = bizRowsRaw.filter((row) => {
      const slug = row.slug as string | null;
      if (!slug || seen.has(slug)) return false;
      seen.add(slug);
      return true;
    });

    // Latest snapshot per project_id.
    const latestByProject = new Map<string, {
      project_id: string;
      overall_health: number | null;
      snapshot_at: string | null;
    }>();
    for (const row of snapshots) {
      if (!latestByProject.has(row.project_id)) {
        latestByProject.set(row.project_id, row);
      }
    }

    let totalArrAud = 0;
    let atRiskCount = 0;
    let latestSnapshotIso: string | null = null;
    for (const biz of bizRows) {
      totalArrAud += Number(biz.arr_aud ?? 0);
      const key = biz.pi_ceo_key ?? biz.slug ?? biz.id;
      const snap = latestByProject.get(key) ?? latestByProject.get(biz.id);
      if (snap?.overall_health !== null && (snap?.overall_health ?? 100) < 60) {
        atRiskCount += 1;
      }
      if (snap?.snapshot_at && (!latestSnapshotIso || snap.snapshot_at > latestSnapshotIso)) {
        latestSnapshotIso = snap.snapshot_at;
      }
    }

    return {
      total_arr_cents: Math.round(totalArrAud * 100),
      at_risk_count: atRiskCount,
      last_rescan: latestSnapshotIso,
      has_live_data: snapshots.length > 0,
      fetched_at: new Date().toISOString(),
    };
  } catch {
    // Single try/catch — Supabase errors, env-var missing, anything — bubbles
    // up as null so the page can render seed mode without crashing.
    return null;
  }
}
