/**
 * SYN-521: Supabase Edge Function — Weekly Calendar Generator
 * Runs every Sunday 18:00 AEDT (08:00 UTC)
 * Cron: 0 8 * * 0
 *
 * Queries all eligible clients (3+ weekly_digests) and generates next week's calendar.
 */

import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const supabaseUrl = Deno.env.get('SUPABASE_URL')!;
const serviceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;

interface EligibleClient {
  id: string;
  business_name: string;
  industry: string;
  brand_voice: string;
  digest_count: number;
}

Deno.serve(async (req: Request) => {
  if (req.method !== 'POST' && req.method !== 'GET') {
    return new Response('Method not allowed', { status: 405 });
  }

  const supabase = createClient(supabaseUrl, serviceKey);

  // Find clients with 3+ digests who don't already have a calendar for next Monday
  const nextMonday = getNextMonday();
  const weekStartStr = nextMonday.toISOString().slice(0, 10);

  const { data: eligibleClients, error: clientsError } = await supabase
    .rpc('get_calendar_eligible_clients', { min_digest_count: 3, week_start: weekStartStr });

  if (clientsError) {
    console.error(JSON.stringify({ event: 'eligible_clients_query_failed', error: clientsError.message }));
    return new Response(JSON.stringify({ error: clientsError.message }), { status: 500 });
  }

  const clients = (eligibleClients as EligibleClient[]) ?? [];
  const results = { generated: 0, skipped: 0, errors: 0 };

  for (const client of clients) {
    try {
      // Call the calendar generation API route
      const apiUrl = `${Deno.env.get('NEXT_PUBLIC_SITE_URL') ?? 'https://synthex.social'}/api/calendar/generate`;
      const res = await fetch(apiUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${serviceKey}`,
        },
        body: JSON.stringify({
          client_id: client.id,
          client_context: {
            business_name: client.business_name,
            industry: client.industry,
            brand_voice: client.brand_voice ?? 'professional',
          },
        }),
      });

      if (res.ok) {
        const body = await res.json() as { skipped_reason?: string };
        if (body.skipped_reason) {
          results.skipped++;
        } else {
          results.generated++;
        }
      } else {
        results.errors++;
      }
    } catch (err) {
      console.error(JSON.stringify({ event: 'client_calendar_error', client_id: client.id, error: String(err) }));
      results.errors++;
    }
  }

  console.log(JSON.stringify({ event: 'calendar_run_complete', week_start: weekStartStr, ...results }));

  return new Response(JSON.stringify({ week_start: weekStartStr, ...results }), {
    headers: { 'Content-Type': 'application/json' },
  });
});

function getNextMonday(): Date {
  const d = new Date();
  const day = d.getDay();
  const daysUntilMonday = day === 1 ? 7 : (8 - day) % 7 || 7;
  d.setDate(d.getDate() + daysUntilMonday);
  d.setHours(0, 0, 0, 0);
  return d;
}
