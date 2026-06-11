export const dynamic = 'force-dynamic';
import { NextRequest, NextResponse } from 'next/server';
import { getAdminClient } from '@/lib/supabase/admin';
import { requireAdmin } from '@/lib/security/require-admin';

function extractSection(content: string, headings: string[]): string {
  for (const h of headings) {
    const regex = new RegExp(`#{1,3}\\s+${h}[\\s\\S]*?(?=^#{1,3}\\s|$)`, 'mi');
    const match = content.match(regex);
    if (match) return match[0].replace(/^#{1,3}[^\n]+\n/, '').trim().slice(0, 400);
  }
  return '';
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ slug: string }> }
) {
  const gate = await requireAdmin(req);
  if (gate instanceof NextResponse) return gate;
  const { slug } = await params;
  const supabase = getAdminClient();

  // Map business slug to wiki page id
  const WIKI_MAP: Record<string, string> = {
    'synthex': 'synthex',
    'restoreassist': 'restore-assist',
    'dr-nrpg': 'dr-nrpg',
    'carsi': 'carsi',
    'ccw-crm': 'ccw',
    'disaster-recovery': 'disaster-recovery',
  };

  const wikiId = WIKI_MAP[slug] ?? slug;
  const { data: page } = await supabase
    .from('wiki_pages')
    .select('id, title, content, updated_at')
    .eq('id', wikiId)
    .single();

  if (!page) return NextResponse.json({ error: 'Wiki page not found', slug }, { status: 404 });

  const content = page.content ?? '';

  // Extract key sections
  const mission = content.split('\n').find((l: string) => l.length > 40 && !l.startsWith('#') && !l.startsWith('-'))?.trim() ?? '';
  const positioning = extractSection(content, ['Positioning', 'Overview', 'What It Is', 'Description']);
  const techStack = extractSection(content, ['Tech Stack', 'Technology', 'Stack', 'Technical']);
  const keyRisks = extractSection(content, ['Key Risks', 'Risks', 'Attention', 'Blockers', 'Needs Attention']);

  return NextResponse.json({
    slug: wikiId,
    businessSlug: slug,
    title: page.title,
    mission: mission.slice(0, 200),
    positioning: positioning.slice(0, 400),
    techStack: techStack.slice(0, 400),
    keyRisks: keyRisks.slice(0, 400),
    lastUpdated: page.updated_at,
    fullContent: content.slice(0, 8000),
  });
}
