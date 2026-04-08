// app/api/sessions/route.ts — list and clear all sessions
export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import { createServerClient } from "@/lib/supabase/server";
import type { Session } from "@/lib/types";

interface SessionRow {
  id: string;
  repo_url: string;
  repo_name: string;
  branch: string;
  pr_url: string | null;
  status: "running" | "done" | "error";
  trigger: "manual" | "webhook" | "cron";
  started_at: string;
  completed_at: string | null;
  result: unknown | null;
}

export async function GET(): Promise<NextResponse<{ sessions: Session[] }>> {
  try {
    const supabase = createServerClient();
    const { data } = await supabase
      .from("sessions")
      .select("id,repo_url,repo_name,branch,pr_url,status,trigger,started_at,completed_at,result")
      .order("started_at", { ascending: false })
      .limit(100);

    const sessions: Session[] = (data as SessionRow[] | null ?? []).map((row) => ({
      id: row.id,
      repoUrl: row.repo_url,
      repoName: row.repo_name,
      branch: row.branch,
      startedAt: new Date(row.started_at).getTime(),
      completedAt: row.completed_at ? new Date(row.completed_at).getTime() : undefined,
      result: row.result as Session["result"],
      previewUrl: undefined,
      phases: [], // populated from result if available
    }));

    return NextResponse.json({ sessions });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Failed to fetch sessions", sessions: [] },
      { status: 500 }
    );
  }
}

export async function DELETE(): Promise<NextResponse> {
  try {
    const supabase = createServerClient();
    await supabase.from("sessions").delete().neq("id", ""); // delete all rows
    return NextResponse.json({ cleared: true });
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : "Failed" }, { status: 500 });
  }
}
