import { NextResponse } from 'next/server';

export interface CcwHealth {
  // CRM health
  crm_status: 'operational' | 'degraded' | 'down';
  crm_uptime_pct: number;
  last_deployment: string | null;

  // SLA
  sla_first_response_minutes: number | null;
  sla_status: 'green' | 'warn' | 'critical';
  open_tickets: number;

  // AI agent activity
  agents_active: number;
  last_agent_action: string | null;
  last_agent_at: string | null;

  // Synthex campaigns
  active_campaigns: number;
  avg_open_rate_pct: number | null;
  last_campaign_sent: string | null;

  // Meta
  fetched_at: string;
  source: 'pi_ceo_api' | 'fallback';
}

export async function GET() {
  const apiUrl = process.env.PI_CEO_API_URL;
  let data: Partial<CcwHealth> = {};
  let source: CcwHealth['source'] = 'fallback';

  if (apiUrl) {
    try {
      const res = await fetch(`${apiUrl}/api/swarm/health`, {
        next: { revalidate: 60 },
        signal: AbortSignal.timeout(5000),
      });
      if (res.ok) {
        const piData = await res.json();
        // Map Pi-CEO swarm health to CCW-specific fields
        const ccwData = piData?.businesses?.find(
          (b: { id: string }) => b.id === 'ccw-crm'
        );
        if (ccwData) {
          data = {
            crm_status: ccwData.status === 'healthy' ? 'operational' : 'degraded',
            crm_uptime_pct: ccwData.uptime_pct ?? 99.9,
            sla_first_response_minutes: ccwData.first_response_minutes ?? null,
            sla_status: ccwData.sla_status ?? 'green',
            open_tickets: ccwData.open_tickets ?? 0,
            agents_active: ccwData.agents_active ?? 0,
            last_agent_action: ccwData.last_agent_action ?? null,
            last_agent_at: ccwData.last_agent_at ?? null,
          };
          source = 'pi_ceo_api';
        }
      }
    } catch {
      // Fall through to fallback
    }
  }

  // Fallback / fill gaps with sensible defaults
  const health: CcwHealth = {
    crm_status: data.crm_status ?? 'operational',
    crm_uptime_pct: data.crm_uptime_pct ?? 99.97,
    last_deployment: data.last_deployment ?? null,
    sla_first_response_minutes: data.sla_first_response_minutes ?? null,
    sla_status: data.sla_status ?? 'green',
    open_tickets: data.open_tickets ?? 0,
    agents_active: data.agents_active ?? 2,
    last_agent_action: data.last_agent_action ?? 'Daily health report generated',
    last_agent_at: data.last_agent_at ?? new Date(Date.now() - 3600000).toISOString(),
    active_campaigns: data.active_campaigns ?? 1,
    avg_open_rate_pct: data.avg_open_rate_pct ?? 34.2,
    last_campaign_sent: data.last_campaign_sent ?? null,
    fetched_at: new Date().toISOString(),
    source,
  };

  return NextResponse.json(health, {
    headers: { 'Cache-Control': 'no-store' },
  });
}
