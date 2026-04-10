// app/api/settings/route.ts — GET (masked read) / POST (upsert) app settings
export const dynamic = "force-dynamic";

import { NextRequest, NextResponse } from "next/server";
import { getSettings, upsertSetting } from "@/lib/supabase/settings";

// GET — returns settings with secrets masked to "SET" / "NOT SET"
export async function GET(): Promise<NextResponse> {
  const s = await getSettings();
  return NextResponse.json({
    github_token:      s.githubToken      ? "SET"     : "NOT SET",
    anthropic_api_key: s.anthropicApiKey  ? "SET"     : "NOT SET",
    analysis_model:    s.analysisModel,
    webhook_secret:    s.webhookSecret    ? "SET"     : "NOT SET",
    cron_repos:        s.cronRepos,
  });
}

// POST — upsert one or more settings
export async function POST(req: NextRequest): Promise<NextResponse> {
  let body: Record<string, string>;
  try { body = await req.json() as Record<string, string>; }
  catch { return NextResponse.json({ error: "Invalid JSON" }, { status: 400 }); }

  const ALLOWED = ["github_token", "anthropic_api_key", "analysis_model", "webhook_secret", "cron_repos", "linear_api_key"];
  const updates: Array<Promise<void>> = [];

  for (const [key, value] of Object.entries(body)) {
    if (!ALLOWED.includes(key)) continue;
    if (typeof value !== "string") continue;
    if (!value.trim()) continue; // skip empty — don't overwrite existing with blank
    updates.push(upsertSetting(key, value.trim()));
  }

  await Promise.allSettled(updates);
  return NextResponse.json({ saved: updates.length });
}
