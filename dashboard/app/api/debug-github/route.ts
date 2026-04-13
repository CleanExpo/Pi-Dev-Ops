// app/api/debug-github/route.ts — runtime diagnostic: confirms which GitHub token is active
// and whether GitHub API calls succeed. DELETE after diagnosis.
export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import { getSettings } from "@/lib/supabase/settings";

export async function GET(): Promise<NextResponse> {
  let settings;
  let settingsError: string | null = null;
  try {
    settings = await getSettings();
  } catch (err) {
    settingsError = err instanceof Error ? err.message : String(err);
  }

  const ghToken = settings?.githubToken || process.env.GITHUB_TOKEN || "";
  const tokenPreview = ghToken
    ? `${ghToken.slice(0, 8)}...${ghToken.slice(-4)} (len=${ghToken.length})`
    : "EMPTY";

  // Test the token against the GitHub API
  let githubStatus: number | null = null;
  let githubBody: unknown = null;
  let githubError: string | null = null;

  if (ghToken) {
    try {
      const res = await fetch("https://api.github.com/user", {
        headers: {
          Authorization: `token ${ghToken}`,
          "User-Agent": "Pi-CEO-Dashboard",
          Accept: "application/vnd.github.v3+json",
        },
      });
      githubStatus = res.status;
      githubBody = await res.json();
    } catch (err) {
      githubError = err instanceof Error ? err.message : String(err);
    }
  }

  return NextResponse.json({
    token_preview: tokenPreview,
    token_source: settings?.githubToken ? "supabase" : process.env.GITHUB_TOKEN ? "env" : "none",
    settings_error: settingsError,
    github_status: githubStatus,
    github_login: (githubBody as Record<string, unknown>)?.login ?? null,
    github_message: (githubBody as Record<string, unknown>)?.message ?? null,
    github_error: githubError,
    env_token_set: !!process.env.GITHUB_TOKEN,
    env_token_preview: process.env.GITHUB_TOKEN
      ? `${process.env.GITHUB_TOKEN.slice(0, 8)}...${process.env.GITHUB_TOKEN.slice(-4)}`
      : "EMPTY",
  });
}
