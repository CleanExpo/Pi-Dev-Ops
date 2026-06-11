// Deno Edge Function — runs every 15 minutes via Supabase cron
// Schedule: */15 * * * *

import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

Deno.serve(async (_req: Request) => {
  const supabaseUrl = Deno.env.get('SUPABASE_URL')!;
  const serviceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
  const supabase = createClient(supabaseUrl, serviceKey);

  const now = new Date().toISOString();

  const { data: items, error } = await supabase
    .from('publish_queue')
    .select('id')
    .in('status', ['pending', 'failed'])
    .lte('scheduled_at', now)
    .lt('attempts', 12)
    .order('scheduled_at', { ascending: true })
    .limit(50);

  if (error) {
    console.error(JSON.stringify({ event: 'queue_fetch_error', error: error.message }));
    return new Response(JSON.stringify({ error: error.message }), { status: 500 });
  }

  if (!items || items.length === 0) {
    return new Response(JSON.stringify({ processed: 0, message: 'No items due' }), { status: 200 });
  }

  const appUrl = Deno.env.get('NEXT_PUBLIC_APP_URL') ?? 'https://synthex.social';
  const secret = Deno.env.get('INTERNAL_API_SECRET') ?? '';

  const processRes = await fetch(`${appUrl}/api/internal/process-publish-queue`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-internal-secret': secret },
    body: JSON.stringify({ item_ids: items.map((i) => i.id) }),
  });

  const result = await processRes.json();
  console.log(JSON.stringify({ event: 'publish_queue_triggered', items_found: items.length, result }));

  return new Response(JSON.stringify(result), { status: 200 });
});
