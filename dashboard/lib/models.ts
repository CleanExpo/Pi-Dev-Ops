// lib/models.ts — Single source of truth for all Claude model names.
//
// When a new model is released, update ONLY this file.
// All routes import from here — no more hunting through 6 files.
//
// Tier logic:
//   ANALYST      — intelligence-heavy tasks: scoring, planning, narrative, ZTE
//   WORKER       — fast/cheap tasks: file listing, inventory, summarisation
//   ORCHESTRATOR — multi-agent coordination, board-level decisions

export const MODELS = {
  // ── Tier 1: Full intelligence ────────────────────────────────────────────────
  ANALYST:      (process.env.ANALYST_MODEL      ?? "claude-sonnet-4-6").trim(),
  ORCHESTRATOR: (process.env.ORCHESTRATOR_MODEL ?? "claude-opus-4-6").trim(),

  // ── Tier 2: Fast/cheap tasks ─────────────────────────────────────────────────
  WORKER:       (process.env.WORKER_MODEL       ?? "claude-haiku-4-5").trim(),

  // ── Default (used by settings, chat, actions) ────────────────────────────────
  DEFAULT:      (process.env.ANALYSIS_MODEL     ?? "claude-sonnet-4-6").trim(),
} as const;

// Phase-to-model mapping for the 8-phase analysis pipeline.
// Phases 1, 2, 4 are listing/summarisation tasks → WORKER tier.
// Phases 3, 5, 6, 7 require deep reasoning → ANALYST tier.
export function phaseModel(phaseId: number, analystModel: string = MODELS.ANALYST): string {
  const WORKER_PHASES = new Set([1, 2, 4]);
  return WORKER_PHASES.has(phaseId) ? MODELS.WORKER : analystModel;
}
