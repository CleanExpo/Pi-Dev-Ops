import { NextResponse } from "next/server";
import path from "node:path";
import { promises as fs } from "node:fs";

export const dynamic = "force-dynamic";

type IntentState = {
  updated_at?: string;
  videos?: Array<{
    video_key: string;
    title?: string;
    channel?: string;
    watch_count_window?: number;
    status?: "accepted" | "excluded";
    reason?: string;
    strategic_hits?: string[];
  }>;
  topics?: Array<{ topic: string; frequency_score: number; confidence: number }>;
  persona_traits?: Array<{ trait: string; confidence: number }>;
  vertical_pathway_signals?: Array<{
    vertical_id: string;
    direction_theme: string;
    strategic_priority: number;
  }>;
  wiki_pages?: string[];
};

function summarize(state: IntentState) {
  const videos = state.videos ?? [];
  const accepted = videos.filter((v) => v.status === "accepted");
  const excluded = videos.filter((v) => v.status === "excluded");
  return {
    updatedAt: state.updated_at ?? null,
    acceptedCount: accepted.length,
    excludedCount: excluded.length,
    topAccepted: accepted
      .slice()
      .sort((a, b) => (b.watch_count_window ?? 1) - (a.watch_count_window ?? 1))
      .slice(0, 10),
    topics: state.topics ?? [],
    personaTraits: state.persona_traits ?? [],
    verticalPathways: state.vertical_pathway_signals ?? [],
    wikiPages: state.wiki_pages ?? [],
    boardUrl: "http://localhost:7119",
  };
}

export async function GET(): Promise<Response> {
  try {
    const statePath = path.join(process.cwd(), ".harness", "ugn_intent_youtube", "state.json");
    const raw = await fs.readFile(statePath, "utf-8");
    const parsed = JSON.parse(raw) as IntentState;
    return NextResponse.json(summarize(parsed));
  } catch {
    return NextResponse.json(
      {
        updatedAt: null,
        acceptedCount: 0,
        excludedCount: 0,
        topAccepted: [],
        topics: [],
        personaTraits: [],
        verticalPathways: [],
        wikiPages: [],
        boardUrl: "http://localhost:7119",
        warning: "No intent catalog state yet. Ingest and synthesize first.",
      },
      { status: 200 },
    );
  }
}
