// app/api/cron/analyze/route.ts — Vercel Cron: weekly scheduled analysis
// Vercel calls this with Authorization: Bearer CRON_SECRET
export const dynamic = "force-dynamic";

import { NextRequest, NextResponse } from "next/server";
import { getSettings } from "@/lib/supabase/settings";

export async function GET(req: NextRequest): Promise<NextResponse> {
  // Verify Vercel cron secret
  const auth = req.headers.get("authorization");
  if (auth !== `Bearer ${process.env.CRON_SECRET}`) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const settings = await getSettings();
  if (settings.cronRepos.length === 0) {
    return NextResponse.json({ skipped: true, reason: "No repos configured — add them in Settings" });
  }

  const host     = req.headers.get("x-forwarded-host") ?? req.headers.get("host") ?? "";
  const protocol = "https";
  const results: Array<{ repo: string; status: string }> = [];

  for (const repoSlug of settings.cronRepos) {
    const repoUrl    = `https://github.com/${repoSlug}`;
    const analyzeUrl = `${protocol}://${host}/api/analyze?repo=${encodeURIComponent(repoUrl)}`;
    try {
      // Fire-and-forget — the SSE stream runs as a separate Vercel function invocation
      fetch(analyzeUrl, { method: "GET", headers: { "x-cron-trigger": "true" } }).catch((e) => console.error(`[cron/analyze] trigger failed for ${repoSlug}`, e));
      results.push({ repo: repoSlug, status: "triggered" });
    } catch {
      results.push({ repo: repoSlug, status: "failed" });
    }
  }

  return NextResponse.json({ triggered: results.length, repos: results });
}
