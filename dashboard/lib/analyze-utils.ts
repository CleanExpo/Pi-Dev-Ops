// lib/analyze-utils.ts — Pure, side-effect-free utilities extracted from app/api/analyze/route.ts
// Keeping these in a separate file lets them be unit-tested without mocking GitHub/Anthropic/Supabase.

/** Parse lessons.jsonl and return the top N most-severe recent lessons as a summary string. */
export function buildLessonsSummary(raw: string, topN = 8): string {
  if (!raw.trim()) return "";
  const lessons: Array<{ severity?: string; source?: string; lesson?: string }> = [];
  for (const line of raw.split("\n")) {
    if (!line.trim()) continue;
    try { lessons.push(JSON.parse(line)); } catch { /* skip malformed */ }
  }
  const rank = (s?: string) => s === "error" ? 0 : s === "warn" ? 1 : 2;
  const top = lessons
    .filter((l) => l.lesson)
    .sort((a, b) => rank(a.severity) - rank(b.severity))
    .slice(0, topN);
  if (!top.length) return "";
  return [
    "=== LESSONS FROM PRIOR RUNS (apply these to improve your analysis) ===",
    ...top.map((l) => `[${l.severity ?? "info"}][${l.source ?? "?"}] ${l.lesson}`),
    "=================================================================",
  ].join("\n");
}

/** Normalise a repo URL and verify it points to github.com. Throws on invalid input. */
export function sanitizeRepoUrl(url: string): string {
  const trimmed = url.trim().replace(/^(?:https?:\/\/)?(?:www\.)?/, "https://");
  if (!/^https:\/\/github\.com\/[\w.-]+\/[\w.-]+/.test(trimmed))
    throw new Error("Invalid GitHub repository URL");
  return trimmed;
}

/** Encode an SSE frame as UTF-8 bytes. */
export function sseEncode(event: string, data: unknown): Uint8Array {
  return new TextEncoder().encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
}
