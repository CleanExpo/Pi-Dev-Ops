export const dynamic = 'force-dynamic';
import { NextRequest, NextResponse } from 'next/server';
import { getAdminClient } from '@/lib/supabase/admin';
import { requireAdmin } from '@/lib/security/require-admin';

export async function GET(req: NextRequest) {
  const gate = await requireAdmin(req);
  if (gate instanceof NextResponse) return gate;
  const supabase = getAdminClient();

  const { data: page } = await supabase
    .from('wiki_pages')
    .select('content')
    .eq('id', 'operational-priorities-q2-2026')
    .single();

  // Parse markdown table rows into priority objects
  const content = page?.content ?? '';
  const tableRegex = /\|\s*(\d+)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|/g;
  const priorities = [];
  let match;
  while ((match = tableRegex.exec(content)) !== null) {
    priorities.push({
      rank: parseInt(match[1]),
      priority: match[2].trim(),
      status: match[3].trim(),
      alertCondition: match[4].trim(),
    });
  }

  // Fallback: hardcoded from wiki knowledge if parsing fails
  if (priorities.length === 0) {
    priorities.push(
      { rank: 1, priority: 'CCW client success — first paying external client', status: 'Active · $33k ARR', alertCondition: 'NPS <60 or response >30min', owner: 'phill' },
      { rank: 2, priority: 'RestoreAssist V1 Cutover — Phase 5 production', status: 'Pending Phill action (RA-1718)', alertCondition: 'Not started by EOW', owner: 'phill' },
      { rank: 3, priority: 'Nexus Wave 1 — CCW portal live', status: 'In progress', alertCondition: 'CCW cannot log in and see data', owner: 'autonomous' },
      { rank: 4, priority: 'NRPG market presence', status: 'DR platform live', alertCondition: 'Adoption velocity stalling', owner: 'autonomous' },
      { rank: 5, priority: 'Synthex prosumer growth', status: '1,000+ users, NRR tracking', alertCondition: 'NRR <100% or churn spike', owner: 'autonomous' },
      { rank: 6, priority: 'CARSI compliance — first implementations', status: 'Deploying', alertCondition: 'GP-team Linear bloat detected', owner: 'autonomous' },
    );
  }

  return NextResponse.json({ priorities, count: priorities.length });
}
