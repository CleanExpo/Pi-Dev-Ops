import { NextResponse } from "next/server";

import { INTENT_ABSENT_MESSAGE, loadIntentState } from "@/lib/command-centre/youtube-intent-state";

export const dynamic = "force-dynamic";

const EMPTY = {
  updatedAt: null,
  acceptedCount: 0,
  excludedCount: 0,
  topAccepted: [],
  topics: [],
  personaTraits: [],
  verticalPathways: [],
  wikiPages: [],
  boardUrl: null,
};

// 200 in every case so the Knowledge deck tile can render; `available` says whether
// the numbers are real. An absent catalogue is the normal state on a deployed host.
export async function GET(): Promise<Response> {
  const load = await loadIntentState();
  if (load.kind === "ok") return NextResponse.json({ ...load.summary, available: true });
  const warning = load.kind === "absent" ? INTENT_ABSENT_MESSAGE : load.message;
  return NextResponse.json({ ...EMPTY, available: false, warning });
}
