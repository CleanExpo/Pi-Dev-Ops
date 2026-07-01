// lib/models.ts — Single source of truth for all Claude model names.
//
// When a new model is released, update ONLY this file.
// All routes import from here — no more hunting through 6 files.
//
// As of July 01 2026: Opus 4.8 · Sonnet 5 · Haiku 4.5
// Tier logic:
//   ANALYST      — intelligence-heavy tasks: scoring, planning, narrative, ZTE
//   WORKER       — fast/cheap tasks: file listing, inventory, summarisation
//   ORCHESTRATOR — multi-agent coordination, board-level decisions

export const MODELS = {
  // ── Tier 1: Full intelligence ────────────────────────────────────────────────
  ANALYST:      (process.env.ANALYST_MODEL      ?? "claude-sonnet-5").trim(),
  ORCHESTRATOR: (process.env.ORCHESTRATOR_MODEL ?? "claude-opus-4-8").trim(),

  // ── Tier 2: Fast/cheap tasks ─────────────────────────────────────────────────
  WORKER:       (process.env.WORKER_MODEL       ?? "claude-haiku-4-5").trim(),

  // ── Default (used by settings, chat, actions) ────────────────────────────────
  DEFAULT:      (process.env.ANALYSIS_MODEL     ?? "claude-sonnet-5").trim(),
} as const;

// Mythos-class models (claude-fable-*, claude-mythos-*) run safety classifiers
// that can decline benign requests with stop_reason "refusal" (HTTP 200, not an
// error). These options make the API retry the request on Opus server-side
// (beta: server-side-fallback-2026-06-01). No-op for non-Mythos models — the
// fallbacks param is only valid on Mythos-class requests.
export function refusalFallback(model: string): {
  params: Record<string, unknown>;
  options: { headers?: Record<string, string> };
} {
  if (!model.startsWith("claude-fable") && !model.startsWith("claude-mythos")) {
    return { params: {}, options: {} };
  }
  return {
    params: { fallbacks: [{ model: "claude-opus-4-8" }] },
    options: { headers: { "anthropic-beta": "server-side-fallback-2026-06-01" } },
  };
}

// Phase-to-model mapping for the 8-phase analysis pipeline.
// Phases 1, 2, 4 are listing/summarisation tasks → WORKER tier.
// Phases 3, 5, 6, 7 require deep reasoning → ANALYST tier.
export function phaseModel(phaseId: number, analystModel: string = MODELS.ANALYST): string {
  const WORKER_PHASES = new Set([1, 2, 4]);
  return WORKER_PHASES.has(phaseId) ? MODELS.WORKER : analystModel;
}
