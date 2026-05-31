import { NextRequest, NextResponse } from 'next/server';
import { requireAdmin } from '@/lib/security/require-admin';

const PI_CEO_URL = process.env.PI_CEO_API_URL || 'https://pi-dev-ops-production.up.railway.app';
const PI_CEO_KEY = process.env.PI_CEO_API_KEY || '';

// Project ID → business name mapping
const PROJECT_MAP: Record<string, { name: string; status_default: string; arr_aud: number }> = {
  'restoreassist':    { name: 'RestoreAssist', status_default: 'building',    arr_aud: 0 },
  'synthex':          { name: 'Synthex',       status_default: 'operational', arr_aud: 0 },
  'ccw-crm':          { name: 'CCW-CRM',       status_default: 'operational', arr_aud: 33000 },
  'disaster-recovery':{ name: 'DR Platform',  status_default: 'operational', arr_aud: 0 },
  'dr-nrpg':          { name: 'NRPG',         status_default: 'building',    arr_aud: 0 },
  'carsi':            { name: 'CARSI',         status_default: 'operational', arr_aud: 0 },
};

async function getPiCeoData() {
  try {
    // Login
    const loginRes = await fetch(`${PI_CEO_URL}/api/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: PI_CEO_KEY }),
      cache: 'no-store',
      signal: AbortSignal.timeout(8000),
    });
    if (!loginRes.ok) return null;

    // Extract session cookie
    const setCookie = loginRes.headers.get('set-cookie') || '';
    const cookieMatch = setCookie.match(/tao_session=([^;]+)/);
    const sessionCookie = cookieMatch ? `tao_session=${cookieMatch[1]}` : '';
    if (!sessionCookie) return null;

    // Fetch project health + autonomy in parallel
    const [projectsRes, autonomyRes] = await Promise.allSettled([
      fetch(`${PI_CEO_URL}/api/projects/health`, {
        headers: { Cookie: sessionCookie },
        cache: 'no-store',
        signal: AbortSignal.timeout(8000),
      }),
      fetch(`${PI_CEO_URL}/api/autonomy/status`, {
        headers: { Cookie: sessionCookie },
        cache: 'no-store',
        signal: AbortSignal.timeout(8000),
      }),
    ]);

    const projects = projectsRes.status === 'fulfilled' && projectsRes.value.ok
      ? await projectsRes.value.json() : [];
    const autonomy = autonomyRes.status === 'fulfilled' && autonomyRes.value.ok
      ? await autonomyRes.value.json() : null;

    return { projects, autonomy };
  } catch {
    return null;
  }
}

function healthToStatus(score: number): 'operational' | 'building' | 'degraded' | 'down' {
  if (score >= 80) return 'operational';
  if (score >= 60) return 'building';
  if (score >= 40) return 'degraded';
  return 'down';
}

export async function GET(req: NextRequest) {
  const gate = await requireAdmin(req);
  if (gate instanceof NextResponse) return gate;
  const piData = PI_CEO_KEY ? await getPiCeoData() : null;

  // Build business health from Pi-CEO data or fallback
  const businesses = Object.entries(PROJECT_MAP).map(([pid, meta]) => {
    const project = piData?.projects?.find((p: { project_id: string }) => p.project_id === pid);
    const health = project?.overall_health ?? 75;
    const security = project?.scores?.security ?? 50;

    return {
      id: pid,
      name: meta.name,
      status: project ? healthToStatus(health) : meta.status_default as 'operational' | 'building' | 'degraded' | 'down',
      uptime_pct: Math.min(99.99, 90 + health * 0.1),
      deploy_frequency: 2,
      open_prs: project?.findings_count?.deployment_health ?? 0,
      ci_passing: security > 30 ? true : (security > 0 ? null : false),
      last_deploy: null,
      arr_aud: meta.arr_aud,
      trend: [health * 0.9, health * 0.92, health * 0.94, health * 0.96, health * 0.97, health * 0.99, health].map(Math.round),
    };
  });

  // Empire score: weighted average of health scores
  const avgHealth = businesses.reduce((s, b) => s + (b.uptime_pct - 90) * 10, 0) / businesses.length;
  const operationalCount = businesses.filter(b => b.status === 'operational').length;
  const score = Math.round((operationalCount / businesses.length) * 60 + avgHealth * 0.4);

  return NextResponse.json({
    score: Math.min(100, Math.max(0, score)),
    businesses,
    total_arr: businesses.reduce((s, b) => s + b.arr_aud, 0),
    active_agents: piData?.autonomy?.poll_count ? Math.min(8, Math.floor(piData.autonomy.poll_count / 50)) : 4,
    content_produced: 40,
    content_total: 85,
    work_orders_open: 0,
    pi_ceo_connected: !!piData,
    autonomy_pct: piData?.autonomy?.effective_autonomy?.effective_autonomy_pct ?? null,
    last_poll_ago_s: piData?.autonomy?.last_poll_ago_s ?? null,
    fetched_at: new Date().toISOString(),
    source: piData ? 'pi_ceo_api' : 'fallback',
  }, { headers: { 'Cache-Control': 'no-store' } });
}
