// intelligence — score trend/competitor signal into the topic queue and return the top angle.
//
// Reuses the same Apify actors as video-director's pre-fill (see references/intelligence.md).
// Scoring is velocity-weighted for short-form. Read-only against production: schema
// inspection + queue reads/writes only, never execute_sql on prod.

export interface ScoredAngle {
  topic: string;
  rationale: string;         // why this angle now (traces to a real signal row)
  queueRef: string;          // video_topic_queue row ref
  score: number;             // 0-100
  breakdown: { freshness: number; fit: number; hookability: number; repurposeReach: number };
  platformsReachable: number; // informs the 8th-platform rule
  reducedSignal?: boolean;    // true when APIFY_API_TOKEN absent (queue-only)
}

// Velocity-weighted: freshness 30 / fit 25 / hookability 25 / repurpose reach 20.
export function scoreAngle(row: {
  freshness: number; fit: number; hookability: number; repurposeReach: number;
}): number {
  const clamp = (n: number, max: number) => Math.max(0, Math.min(max, n));
  return (
    clamp(row.freshness, 30) +
    clamp(row.fit, 25) +
    clamp(row.hookability, 25) +
    clamp(row.repurposeReach, 20)
  );
}

export async function scoreTopicQueue(args: {
  orgId: string;
  topic: string | "auto";
}): Promise<ScoredAngle> {
  // 1. If APIFY_API_TOKEN present: refresh video_topic_queue from the actors in
  //    references/intelligence.md (Shorts/TikTok/Reels velocity + comment-mined pains).
  //    Else: run on existing video_topic_queue / tracked_competitors / content_topic_suggestions
  //    rows and set reducedSignal.
  // 2. Score every candidate with scoreAngle(); write score + breakdown back to the row.
  // 3. If topic === "auto": return the top-scored row. Else: score the named topic and
  //    return it, surfacing its score so the choice is informed, not blind.
  //
  // Implementation binds to the org's Supabase project via the app's data layer — NOT via
  // execute_sql against production. Kept as the documented contract; the runner wires it.
  throw new Error("scoreTopicQueue: wire to the org data layer (see references/intelligence.md)");
}
