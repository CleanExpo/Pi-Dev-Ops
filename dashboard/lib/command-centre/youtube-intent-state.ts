// Shared loader for the UG-N YouTube intent catalogue.
//
// The catalogue is produced on the local mesh machine and written to
// `.harness/ugn_intent_youtube/state.json`. On a deployed host that file does not
// exist, so "absent" is the normal production state and must be said plainly —
// never shown as a live zero, and never as a raw ENOENT carrying a server path.
// The Excalidraw board runs on localhost, so it is only linked outside production.

import path from "node:path";
import { promises as fs } from "node:fs";

interface IntentVideo {
  video_key: string;
  title?: string;
  channel?: string;
  watch_count_window?: number;
  status?: "accepted" | "excluded";
  strategic_hits?: string[];
}

interface IntentState {
  updated_at?: string;
  videos?: IntentVideo[];
  topics?: Array<{ topic: string; frequency_score: number; confidence: number }>;
  persona_traits?: Array<{ trait: string; confidence: number }>;
  vertical_pathway_signals?: Array<{ vertical_id: string; direction_theme: string; strategic_priority: number }>;
  wiki_pages?: string[];
}

export interface IntentSummary {
  updatedAt: string | null;
  acceptedCount: number;
  excludedCount: number;
  topAccepted: IntentVideo[];
  topics: NonNullable<IntentState["topics"]>;
  personaTraits: NonNullable<IntentState["persona_traits"]>;
  verticalPathways: NonNullable<IntentState["vertical_pathway_signals"]>;
  wikiPages: string[];
  boardUrl: string | null;
}

export type IntentLoad =
  | { kind: "ok"; summary: IntentSummary }
  | { kind: "absent" }
  | { kind: "error"; message: string };

export const INTENT_ABSENT_MESSAGE =
  "Not available on this host. The intent catalogue is produced on the local mesh machine and is not deployed.";

const LOCAL_BOARD_URL = "http://localhost:7119";

export function intentStatePath(): string {
  return path.join(process.cwd(), ".harness", "ugn_intent_youtube", "state.json");
}

export function summarizeIntent(state: IntentState, isProduction: boolean): IntentSummary {
  const videos = state.videos ?? [];
  const accepted = videos.filter((v) => v.status === "accepted");
  return {
    updatedAt: state.updated_at ?? null,
    acceptedCount: accepted.length,
    excludedCount: videos.filter((v) => v.status === "excluded").length,
    topAccepted: accepted
      .slice()
      .sort((a, b) => (b.watch_count_window ?? 1) - (a.watch_count_window ?? 1))
      .slice(0, 10),
    topics: state.topics ?? [],
    personaTraits: state.persona_traits ?? [],
    verticalPathways: state.vertical_pathway_signals ?? [],
    wikiPages: state.wiki_pages ?? [],
    boardUrl: isProduction ? null : LOCAL_BOARD_URL,
  };
}

function isMissingFile(e: unknown): boolean {
  return typeof e === "object" && e !== null && (e as { code?: unknown }).code === "ENOENT";
}

export async function loadIntentState(
  read: (p: string) => Promise<string> = (p) => fs.readFile(p, "utf-8"),
  isProduction: boolean = process.env.NODE_ENV === "production",
): Promise<IntentLoad> {
  let raw: string;
  try {
    raw = await read(intentStatePath());
  } catch (e) {
    if (isMissingFile(e)) return { kind: "absent" };
    return { kind: "error", message: "The intent catalogue file could not be read." };
  }
  try {
    return { kind: "ok", summary: summarizeIntent(JSON.parse(raw) as IntentState, isProduction) };
  } catch {
    return { kind: "error", message: "The intent catalogue file is not valid JSON." };
  }
}
