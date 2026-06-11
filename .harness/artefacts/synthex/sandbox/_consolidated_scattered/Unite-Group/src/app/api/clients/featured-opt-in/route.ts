export const dynamic = 'force-dynamic';
import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { requireAdmin } from '@/lib/security/require-admin';

export async function PATCH(request: NextRequest) {
  const gate = await requireAdmin(request);
  if (gate instanceof NextResponse) return gate;

  const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  );

  let body: { client_id: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  if (!body.client_id) {
    return NextResponse.json({ error: 'client_id required' }, { status: 400 });
  }

  // Update status to 'applied'
  const { error: updateError } = await supabase
    .from('clients')
    .update({ featured_programme_status: 'applied' })
    .eq('id', body.client_id)
    .eq('featured_programme_status', 'not_applied'); // only if not already applied

  if (updateError) {
    console.error(JSON.stringify({ event: 'featured_opt_in_error', error: updateError.message }));
    return NextResponse.json({ error: 'Update failed' }, { status: 500 });
  }

  // Fetch client name + best metric for the Slack alert
  const { data: client } = await supabase
    .from('clients')
    .select('name')
    .eq('id', body.client_id)
    .single();

  const { data: digests } = await supabase
    .from('weekly_digests')
    .select('avg_engagement_rate, best_platform')
    .eq('client_id', body.client_id)
    .order('avg_engagement_rate', { ascending: false })
    .limit(1);

  const bestEngagement = digests?.[0]?.avg_engagement_rate;
  const bestPlatform = digests?.[0]?.best_platform;

  // Fire Slack alert
  const webhookUrl = process.env.SLACK_FEATURED_CLIENTS_WEBHOOK_URL;
  if (webhookUrl) {
    const slackMessage = {
      text: `🎬 *New Featured in Synthex application*\n*Client:* ${client?.name ?? body.client_id}${bestEngagement ? `\n*Best metric:* ${(bestEngagement * 100).toFixed(1)}% avg engagement on ${bestPlatform ?? 'social'}` : ''}`,
    };

    await fetch(webhookUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(slackMessage),
    }).catch((err) => {
      console.error(JSON.stringify({ event: 'slack_alert_error', error: err.message }));
    });
  }

  console.log(JSON.stringify({ event: 'featured_opt_in_success', client_id: body.client_id }));

  return NextResponse.json({ ok: true });
}
