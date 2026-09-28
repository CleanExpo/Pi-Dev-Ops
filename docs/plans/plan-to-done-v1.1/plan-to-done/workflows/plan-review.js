// STATUS: DRAFT_UNTESTED. Written against the documented workflow script API
// (https://code.claude.com/docs/en/workflows): agent(), pipeline(), parallel(),
// phase(), log(), the `args` global, and the `schema` option. Run
// /workflow-authoring before editing, then save via /workflows → s, or copy to
// .claude/workflows/plan-review.js and /reload-skills.
//
// Purpose: replace the "independent review: NOT_RUN" placeholder for the
// same-model-family half of review with an adversarial, clean-context workflow.
// The cross-model half (Codex read-only) still runs outside this script.
//
// Invocation: /plan-review {"plan_dir": "docs/plans/<mission>/", "commit": "<sha>", "patch_id": "<git patch-id>"}
// No Date.now()/Math.random(): the runtime throws on them so relaunches replay.

export const meta = {
  name: 'plan-review',
  description: 'Adversarially review a plan-to-done packet: coverage, evidence, boundary, false-finish claims',
  phases: ['Inventory', 'Challenge', 'Cross-check', 'Verdict'],
}

const planDir = args?.plan_dir ?? 'docs/plans/'

phase('Inventory')
const inventory = await agent(
  `List every Markdown and JSON file under ${planDir}. For each, return its path and the
   document responsibility it claims (intent, current-state, coverage, spec, engineering,
   implementation-plan, verification, release-ops, decisions, handoff, other). Read only.`,
  {
    label: 'inventory',
    schema: {
      type: 'object', required: ['files'],
      properties: { files: { type: 'array', items: { type: 'object',
        required: ['path', 'responsibility'],
        properties: { path: { type: 'string' }, responsibility: { type: 'string' } } } } },
    },
  },
)
if (!inventory) return { status: 'BLOCKED', reason: 'inventory agent returned null' }

phase('Challenge')
// One adversarial reviewer per document, each with a clean context and one job.
const findings = await pipeline(inventory.files, f =>
  agent(
    `You are an adversarial reviewer. Read ${f.path} (responsibility: ${f.responsibility}).
     Report ONLY defects from this list, with a quote and line reference for each:
     required outcome missing; journey ends before its user-visible result; interface with
     one side only; unverifiable acceptance criterion; release or recovery omitted;
     critical assumption without owner; existing work silently replaced; approval boundary
     changed by the writer; a product COMPLETE / SHIPPED / verified claim without cited
     evidence; a claim that a file, screen, endpoint or passed test proves a connected user
     journey works. Do not propose fixes. Do not write files.`,
    {
      label: f.path,
      schema: {
        type: 'object', required: ['path', 'defects'],
        properties: { path: { type: 'string' }, defects: { type: 'array', items: { type: 'object',
          required: ['kind', 'quote', 'severity'],
          properties: { kind: { type: 'string' }, quote: { type: 'string' },
            location: { type: 'string' }, severity: { type: 'string', enum: ['blocking', 'major', 'minor'] } } } } },
      },
    },
  ),
)
const usable = findings.filter(Boolean)

phase('Cross-check')
// A second, independent pass verifies each blocking/major defect against the source text
// so a hallucinated defect does not become a blocker.
const verified = await pipeline(
  usable.flatMap(r => r.defects.filter(d => d.severity !== 'minor').map(d => ({ ...d, path: r.path }))),
  d => agent(
    `Open ${d.path}. Does the quoted text "${d.quote}" appear, and does it actually exhibit
     the defect "${d.kind}"? Answer confirmed=true only if both hold. Read only.`,
    { label: `${d.path}:${d.kind}`,
      schema: { type: 'object', required: ['confirmed'],
        properties: { confirmed: { type: 'boolean' }, note: { type: 'string' } } } },
  ),
)

phase('Verdict')
const confirmed = verified.filter(v => v && v.confirmed).length
const rejected = verified.filter(v => v && !v.confirmed).length
log(`confirmed ${confirmed}, rejected ${rejected} candidate defects`)

// The workflow reports; it does not change planning status, grant authority, or edit files.
return {
  review_kind: 'same-family-clean-context',
  reviewed_commit: args?.commit ?? null,
  reviewed_patch_id: args?.patch_id ?? null,
  documents: inventory.files.length,
  candidate_defects: usable.reduce((n, r) => n + r.defects.length, 0),
  confirmed_defects: confirmed,
  rejected_candidates: rejected,
  findings: usable,
  verification: verified.filter(Boolean),
  note: 'Advisory. A cross-model review (Codex, read-only) is still required for an independent-review receipt.',
}
