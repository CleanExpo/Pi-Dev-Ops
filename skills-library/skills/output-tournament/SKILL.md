---
name: output-tournament
description: Use when a creative brief has multiple plausible directions and picking wrong is costly — landing-page hero copy, taglines, headlines, hooks, video concepts, design directions. Generate several diverging variants, judge them independently, synthesise a winner. Not for high-stakes decisions or cross-domain review of one shared draft.
---

# output-tournament — generate, judge, synthesise

For ONE creative artifact where several genuinely different directions are plausible.
Cheap parallel variants beat one deeply-reasoned draft; independent judging beats
self-grading; the winner is synthesised, never blind-shipped or concatenated.

## When to invoke

- Marketing copy, headlines, taglines, hooks, landing-page hero sections
- Video concepts, design directions, campaign angles
- Any single creative artifact where "which direction" is the open question

## When NOT to invoke

- High-stakes decisions (architecture, strategy) — use `boardroom` instead
  (multi-model triangulation on one answer, not variant generation)
- Cross-domain review of one shared draft (copy that must satisfy SEO + brand +
  E-E-A-T at once) — use `specialist-council` instead (specialists advise on one
  artifact, they don't each produce a competing one)
- Routine drafts where one direction is obviously correct — just write it

## 1. Generate

Dispatch 3-5 sub-agents in parallel, each briefed with ONE distinct creative angle.
Lenses must be genuinely divergent — not paraphrases of each other. For copy, use
angles like:

- **Benefit-led** — leads with the outcome the reader gets
- **Story-led** — leads with a scenario or narrative
- **Contrarian** — challenges the obvious framing
- **Radically-minimal** — strips to the fewest words that still land

Route generation through the domain skill that fits (`marketing-copywriter`,
`brand-ambassador`, `design-board`) — one variant per agent, one lens per agent.

Run each generator at deliberately LOW-to-MEDIUM reasoning effort. This is
intentional: diversity plus speed plus cost is the alpha at this stage — five
quick divergent drafts beat one deeply-reasoned draft, because the judge-and-synthesise
steps recover the quality a single high-effort pass would have front-loaded.

## 2. Score

Score every variant with the `judge` skill's rubric (evidence-ranked, multi-lens).
The agent that generated a variant never scores its own work — scoring is always
independent of generation. Capture per variant: a numeric or ranked score, plus a
one-line rationale.

## 3. Synthesise

Take the top-scored variant as the base. Graft the strongest elements of the
runners-up into it.

Hard rules:

- Never blind-ship the #1 variant unexamined — synthesis is mandatory, not optional
- Never concatenate variants — synthesis means selective grafting into one
  coherent artifact, not stitching multiple drafts together

## 4. Bound + emit

One synthesis round only — no iterative re-tournaments. The owner (human or
calling agent) makes the final call on the synthesised output.

Return:

- The winning artifact
- A tournament record: each variant, its score, and what (if anything) was
  grafted from it into the winner

## Anti-duplication

Reuses `judge` for scoring and the existing generation-domain skills
(`marketing-copywriter`, `brand-ambassador`, `design-board`) for variant
production. No new tools, no new infra, no new file formats.
