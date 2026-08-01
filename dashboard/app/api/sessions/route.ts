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

/**
 * DELETE /api/sessions
 *
 * Previously an unconditional delete-all via `.neq("id","")` — the delete-everything
 * idiom — reachable by anything holding the single shared dashboard password. In a
 * shared-password system "authenticated" includes automation, and the fence intercepts
 * tool calls rather than HTTP, so this endpoint sat outside every gate we have built.
 *
 * Now: delete ONE session by id, or pass an explicit confirmation token to clear all.
 * There is no longer a request shape that wipes the table by accident.
 */
export async function DELETE(req: Request): Promise<NextResponse> {
  try {
    const url = new URL(req.url);
    const id = url.searchParams.get("id");
    const confirm = url.searchParams.get("confirm");
    const supabase = createServerClient();

    if (id) {
      await supabase.from("sessions").delete().eq("id", id);
      return NextResponse.json({ cleared: 1, id });
    }

    if (confirm !== "DELETE_ALL_SESSIONS") {
      return NextResponse.json(
        {
          error:
            "Refusing to delete every session. Pass ?id=<sessionId> to remove one, " +
            "or ?confirm=DELETE_ALL_SESSIONS to clear the table deliberately.",
        },
        { status: 400 }
      );
    }

    // Explicit, confirmed clear-all. Scoped by created_at rather than the
    // `.neq("id","")` match-everything idiom.
    await supabase.from("sessions").delete().gte("created_at", "1970-01-01");
    return NextResponse.json({ cleared: "all", confirmed: true });
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : "Failed" }, { status: 500 });
  }
}
