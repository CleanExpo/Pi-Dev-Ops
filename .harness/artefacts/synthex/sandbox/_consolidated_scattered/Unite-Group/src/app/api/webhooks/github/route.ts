// @ts-nocheck
// POST /api/webhooks/github — GitHub webhook receiver for PR-triggered Proof Videos.
//
// Listens for `pull_request.closed` (merged) events on Unite-Group-managed
// repos. When a PR is merged with the `client-visible` label, we:
//   1. Verify the X-Hub-Signature-256 HMAC
//   2. Extract: PR metadata, linked Linear issue, Vercel preview URL
//   3. Resolve `client_slug` + `brand_slug` from the repo (via REPO_TO_CLIENT)
//   4. Build a production_brief.json matching the video-director SKILL.md schema
//   5. Insert into video_production_queue → pending
//   6. Single-shot Telegram ping via @PiCeoMarketingBot
//
// The Pi-CEO swarm worker drains the queue and dispatches the Video Agency.
//
// Set GITHUB_WEBHOOK_SECRET in Vercel + ~/.hermes/.env. Configure each repo's
// webhook URL to https://unite-group.in/api/webhooks/github with that secret.
import { NextRequest, NextResponse } from 'next/server';
import { getAdminClient } from '@/lib/supabase/admin';
import { safeError } from '@/lib/safeError';
import crypto from 'crypto';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';
export const maxDuration = 30;

const WEBHOOK_SECRET = process.env.GITHUB_WEBHOOK_SECRET;

// Repo → (client_slug, brand_slug, default_composition, default_channel)
// Add new client repos here as engagements onboard.
const REPO_TO_CLIENT: Record<string, {
  client_slug: string;
  brand_slug: string;
  default_composition: 'weekly-proof' | 'social-hook' | 'b-roll-cinematic';
  default_channel: 'portal-embed' | 'linkedin' | 'ig-reel';
}> = {
  'cleanexpo/dimitri-itr':        { client_slug: 'dimitri-itr',     brand_slug: 'dimitri',          default_composition: 'weekly-proof',     default_channel: 'portal-embed' },
  'cleanexpo/ccw-crm':            { client_slug: 'ccw',             brand_slug: 'ccw',              default_composition: 'weekly-proof',     default_channel: 'portal-embed' },
  'cleanexpo/bulcs-holdings':     { client_slug: 'bulcs-holdings',  brand_slug: 'bulcs',            default_composition: 'social-hook',      default_channel: 'linkedin' },
  'cleanexpo/restoreassist':      { client_slug: 'restoreassist',   brand_slug: 'restoreassist',    default_composition: 'weekly-proof',     default_channel: 'portal-embed' },
  'cleanexpo/dr-platform':        { client_slug: 'dr-platform',     brand_slug: 'dr-platform',      default_composition: 'weekly-proof',     default_channel: 'portal-embed' },
  'cleanexpo/dr-nrpg':            { client_slug: 'nrpg',            brand_slug: 'nrpg',             default_composition: 'weekly-proof',     default_channel: 'portal-embed' },
  'cleanexpo/carsi':              { client_slug: 'carsi',           brand_slug: 'carsi',            default_composition: 'weekly-proof',     default_channel: 'portal-embed' },
  'cleanexpo/Unite-Group':        { client_slug: 'unite-group',     brand_slug: 'unite-group',      default_composition: 'social-hook',      default_channel: 'linkedin' },
};

function verifySignature(payload: string, signature: string | null): boolean {
  if (!WEBHOOK_SECRET || !signature) return false;
  const expected = 'sha256=' + crypto
    .createHmac('sha256', WEBHOOK_SECRET)
    .update(payload, 'utf8')
    .digest('hex');
  // Length-check pre-empts timingSafeEqual throwing on mismatched buffers
  // (deepsec P1 — the throw was caught silently which made shape errors
  // indistinguishable from signature errors).
  const sigBuf = Buffer.from(signature);
  const expBuf = Buffer.from(expected);
  if (sigBuf.length !== expBuf.length) return false;
  return crypto.timingSafeEqual(sigBuf, expBuf);
}

function extractLinearIssue(prBody: string | null | undefined): string | null {
  if (!prBody) return null;
  // Match "Closes UNI-1234" / "Fixes RA-567" / "Linear: PRJ-89" patterns
  const m = prBody.match(/\b(?:closes?|fixes?|resolves?|linear:?)\s+([A-Z]{2,4}-\d+)/i);
  return m ? m[1].toUpperCase() : null;
}

async function findVercelPreviewUrl(repo: string, prNumber: number, token: string | undefined): Promise<string | null> {
  if (!token) return null;
  try {
    const r = await fetch(
      `https://api.github.com/repos/${repo}/issues/${prNumber}/comments?per_page=100`,
      { headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json' } }
    );
    if (!r.ok) return null;
    const comments = await r.json();
    // Vercel bot posts a comment with the preview URL — extract any `*.vercel.app` URL.
    // Strict equality on `'vercel[bot]'` (deepsec P1): substring `includes('vercel')`
    // would let `vercel-hater` or `i-spoof-vercel` seed a malicious preview URL.
    for (const c of comments) {
      if (c.user?.login === 'vercel[bot]') {
        const m = (c.body as string).match(/https:\/\/[a-z0-9-]+\.vercel\.app[^\s)]*/);
        if (m) return m[0];
      }
    }
  } catch {
    return null;
  }
  return null;
}

function buildProductionBrief(opts: {
  client_slug: string;
  brand_slug: string;
  composition: string;
  channel: string;
  pr_title: string;
  pr_url: string;
  pr_body: string | null | undefined;
  linear_issue: string | null;
  preview_url: string | null;
}) {
  const composition_durations: Record<string, number> = {
    'weekly-proof':      90,
    'social-hook':       30,
    'b-roll-cinematic': 180,
  };
  const aspect_ratios: Record<string, string> = {
    'portal-embed': '16:9',
    'linkedin':     '1:1',
    'ig-reel':      '9:16',
  };
  return {
    job_id: `${opts.client_slug}-${Date.now()}-pr${opts.pr_url.split('/').pop()}`,
    brand: opts.brand_slug,
    composition_type: opts.composition,
    story_sentence: opts.pr_title.slice(0, 120),
    channel: opts.channel,
    duration_seconds: composition_durations[opts.composition] ?? 60,
    aspect_ratio: aspect_ratios[opts.channel] ?? '16:9',
    feeling: opts.composition === 'b-roll-cinematic' ? 'confident' : 'curious',
    cta: 'See it live',
    must_include: [
      opts.linear_issue ? `Linear ticket ${opts.linear_issue}` : null,
      opts.preview_url ? 'Live preview URL' : null,
    ].filter(Boolean),
    must_avoid: ['placeholder text', 'lorem ipsum'],
    brandconfig_path: `Synthex/packages/brand-config/src/brands/${opts.brand_slug}.ts`,
    voice_clone_id: 'phill-elevenlabs-pro',
    delivery: {
      channel: 'portal+email',
      due: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
    },
    source: {
      pr_url: opts.pr_url,
      linear_issue: opts.linear_issue,
      preview_url: opts.preview_url,
    },
  };
}

export async function POST(request: NextRequest) {
  if (!WEBHOOK_SECRET) {
    return NextResponse.json({ error: 'webhook not configured' }, { status: 503 });
  }

  // 1. Verify signature
  const signature = request.headers.get('x-hub-signature-256');
  const rawBody = await request.text();
  if (!verifySignature(rawBody, signature)) {
    return NextResponse.json({ error: 'invalid signature' }, { status: 401 });
  }

  const event = request.headers.get('x-github-event');
  const deliveryId = request.headers.get('x-github-delivery');

  // 2. Filter — only pull_request.closed + merged
  if (event !== 'pull_request') {
    return NextResponse.json({ received: true, skipped: 'not-pr-event' }, { status: 200 });
  }

  // 2a. Idempotency pre-check (deepsec P1): the outbound GitHub comments
  //     fetch below can take up to 30s; under retry, the same delivery_id
  //     could enqueue twice before the UNIQUE index sees it. Catching the
  //     duplicate here saves the API call AND the 5xx path.
  if (deliveryId) {
    const adminPre = getAdminClient();
    const { data: dup } = await adminPre
      .from('video_production_queue')
      .select('id')
      .eq('github_delivery_id', deliveryId)
      .maybeSingle();
    if (dup) {
      return NextResponse.json({ received: true, idempotent: true }, { status: 200 });
    }
  }

  let body: any;
  try {
    body = JSON.parse(rawBody);
  } catch {
    return NextResponse.json({ error: 'invalid JSON' }, { status: 400 });
  }

  const action = body.action;
  const pr = body.pull_request;
  if (action !== 'closed' || !pr?.merged) {
    return NextResponse.json({ received: true, skipped: `action=${action} merged=${pr?.merged}` }, { status: 200 });
  }

  // 3. Filter — must have `client-visible` label
  const labels: string[] = (pr.labels ?? []).map((l: any) => l.name);
  if (!labels.includes('client-visible')) {
    return NextResponse.json({ received: true, skipped: 'no-client-visible-label' }, { status: 200 });
  }

  // 4. Resolve client routing from repo
  const repoFullName = body.repository?.full_name;
  const routing = REPO_TO_CLIENT[repoFullName];
  if (!routing) {
    return NextResponse.json({ received: true, skipped: `repo-not-in-routing:${repoFullName}` }, { status: 200 });
  }

  // 5. Enrich: Linear issue + Vercel preview URL
  const linearIssue = extractLinearIssue(pr.body);
  const previewUrl = await findVercelPreviewUrl(
    repoFullName, pr.number, process.env.GITHUB_TOKEN
  );

  // 6. Build the production brief
  const brief = buildProductionBrief({
    client_slug: routing.client_slug,
    brand_slug: routing.brand_slug,
    composition: routing.default_composition,
    channel: routing.default_channel,
    pr_title: pr.title,
    pr_url: pr.html_url,
    pr_body: pr.body,
    linear_issue: linearIssue,
    preview_url: previewUrl,
  });

  // 7. Insert into queue
  const admin = getAdminClient();
  const { data, error } = await admin
    .from('video_production_queue')
    .insert({
      trigger: 'pr-merge',
      source_repo: repoFullName,
      source_pr_number: pr.number,
      source_pr_url: pr.html_url,
      source_pr_title: pr.title,
      source_linear_issue: linearIssue,
      source_preview_url: previewUrl,
      client_slug: routing.client_slug,
      brand_slug: routing.brand_slug,
      composition_type: routing.default_composition,
      channel: routing.default_channel,
      duration_seconds: brief.duration_seconds,
      production_brief: brief,
      status: 'pending',
      metadata: { github_delivery_id: deliveryId },
    })
    .select('id, client_slug, composition_type')
    .single();

  if (error) {
    // UNIQUE on github_delivery_id (migration 20260514170000) absorbs the
    // residual race where the pre-check missed but the insert hits a
    // concurrent retry. Treat as idempotent success.
    if ((error as any).code === '23505') {
      return NextResponse.json({ received: true, idempotent: true }, { status: 200 });
    }
    return NextResponse.json(safeError('queue_insert_failed', error), { status: 500 });
  }

  return NextResponse.json({
    received: true,
    queued: true,
    queue_id: data.id,
    client_slug: data.client_slug,
    composition_type: data.composition_type,
    next: 'The Pi-CEO Video Agency will produce + deliver within 24h.',
  }, { status: 201 });
}
