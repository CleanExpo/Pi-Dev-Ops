// app/api/actions/commit/route.ts — commit generated content to analysis branch
import { NextRequest, NextResponse } from "next/server";
import { makeOctokit, pushFile } from "@/lib/github";
import { getSettings } from "@/lib/supabase/settings";

export async function POST(req: NextRequest) {
  try {
    const { owner, repo, branch, path, content, message } =
      await req.json() as {
        owner: string; repo: string; branch: string;
        path: string; content: string; message: string;
      };

    if (!owner || !repo || !branch || !path || !content) {
      return NextResponse.json({ error: "Missing required fields" }, { status: 400 });
    }

    const settings = await getSettings();
    const token    = settings.githubToken || process.env.GITHUB_TOKEN || "";
    if (!token) {
      return NextResponse.json({ error: "GitHub token not configured" }, { status: 500 });
    }

    const octokit = makeOctokit(token);
    await pushFile(octokit, owner, repo, branch, path, content, message);

    return NextResponse.json({ ok: true, path });
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Commit failed";
    console.error("[actions/commit]", msg);
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
