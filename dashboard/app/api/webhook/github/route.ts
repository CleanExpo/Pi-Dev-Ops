// app/api/webhook/github/route.ts — receives GitHub push/PR events, triggers analysis
export const dynamic = "force-dynamic";

import { NextRequest, NextResponse } from "next/server";
import { createHmac, timingSafeEqual } from "crypto";
import { getSettings } from "@/lib/supabase/settings";
import { parseRepoUrl } from "@/lib/github";

interface GitHubPayload {
  repository?: { html_url?: string; full_name?: string };
  ref?:        string;
}

export async function POST(req: NextRequest): Promise<NextResponse> {
  const rawBody  = await req.text();
  const sig256   = req.headers.get("x-hub-signature-256") ?? "";
  const event    = req.headers.get("x-github-event") ?? "";

  // Only handle push and pull_request events
  if (!["push", "pull_request"].includes(event)) {
    return NextResponse.json({ skipped: true, reason: `Unsupported event: ${event}` });
  }

  // Verify HMAC-SHA256 signature
  const settings = await getSettings();
  if (!settings.webhookSecret) {
    return NextResponse.json({ error: "Webhook secret not configured — add it in Settings" }, { status: 500 });
  }

  const expectedHex = createHmac("sha256", settings.webhookSecret).update(rawBody).digest("hex");
  const expected    = `sha256=${expectedHex}`;

  // Pad to equal length before timing-safe compare
  const maxLen  = Math.max(sig256.length, expected.length);
  const sigBuf  = Buffer.from(sig256.padEnd(maxLen));
  const expBuf  = Buffer.from(expected.padEnd(maxLen));
  if (!timingSafeEqual(sigBuf, expBuf)) {
    return NextResponse.json({ error: "Invalid signature" }, { status: 401 });
  }

  // Parse payload
  let payload: GitHubPayload;
  try { payload = JSON.parse(rawBody) as GitHubPayload; }
  catch { return NextResponse.json({ error: "Invalid JSON payload" }, { status: 400 }); }

  const repoUrl = payload.repository?.html_url;
  if (!repoUrl) return NextResponse.json({ error: "No repository URL in payload" }, { status: 400 });

  const { owner, repo } = parseRepoUrl(repoUrl);

  // Build internal analyze URL and fire-and-forget (SSE stream runs independently)
  const host     = req.headers.get("x-forwarded-host") ?? req.headers.get("host") ?? "localhost:3000";
  const protocol = host.includes("localhost") ? "http" : "https";
  const analyzeUrl = `${protocol}://${host}/api/analyze?repo=${encodeURIComponent(repoUrl)}`;

  fetch(analyzeUrl, {
    method:  "GET",
    headers: { "x-webhook-trigger": "github" },
  }).catch(() => {});

  return NextResponse.json({ triggered: true, repo: `${owner}/${repo}`, event });
}
