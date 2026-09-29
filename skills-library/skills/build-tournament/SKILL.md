---
name: build-tournament
description: Compete-mode for BUILT artifacts — landing page, component, small app, email template. Type /build-tournament <brief> to have isolated persona contestants each build the full artifact, a blind judge score them, and a revised champion ship. Reserve for high-stakes builds; one-shot first for routine work.
argument-hint: "<the build brief — artifact, audience, constraints, success criteria>"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Bash, Write, Edit, Agent, Workflow, Skill
---

# build-tournament — isolated contestants, blind judge, revised champion

Angela Jiang's (Anthropic head of product) compete mode: N isolated sub-agents each build the
COMPLETE artifact from the same brief, a blind judge scores them against pre-declared criteria,
and the champion is revised with the judge's feedback plus grafts from the losers. The revision
round is where the quality comes from — raw contestant scores cluster within a few points.

## When to invoke

- A high-stakes built artifact (landing page, dashboard screen, component, small app, branded
  template) where direction AND execution are both open and picking wrong is costly.
- You are about to one-shot a client-facing or launch-critical build — stop and run this instead.
- NOT for routine builds: a bare one-shot with the playbook in context is the baseline; this
  costs ~4x tokens and wall-clock, so the artifact must earn it.

## Core procedure — DO NOT DEVIATE

1. **Lock the brief and criteria BEFORE spawning.** Write the full business brief (product,
   audience, CTA, constraints) and 4-6 scoring criteria with weights. Criteria declared after
   seeing output is judge contamination. UI artifact → run `mobbin-ui-patterns` first and put
   the reference brief inside the contestant brief (founder directive 2026-07-13).
   - Done when: brief + weighted rubric exist in a file contestants and judge both receive.
2. **Spawn 3 isolated contestants** via the Workflow tool (this skill's instruction satisfies
   its opt-in gate), one persona each, identical brief, `isolation: 'worktree'` when they write
   files, and explicit rules: complete the whole artifact, never ask for direction, never look
   at sibling work. Personas — genuinely divergent lenses, not paraphrases:
   - **Operator** — ships the most usable, conversion-mechanical version.
   - **Strategist** — optimises for positioning, narrative, and differentiation.
   - **Skeptic** — builds for the distrustful visitor; removes waffle, proves claims.
   - Done when: three complete artifacts exist, none has seen another.
3. **Blind-judge.** One fresh judge agent (never a contestant) receives the artifacts labeled
   A/B/C with personas stripped, scores each against the rubric using the `judge` skill's
   evidence-ranked manner, and returns per-criterion scores + specific defects + strongest
   element of each artifact.
   - Done when: scored table + defect list + graft candidates exist.
4. **Champion revision — mandatory, the actual alpha.** Take the winner, apply the judge's
   defect list, graft the named strongest elements from the losers. Never blind-ship the raw
   winner; never concatenate artifacts. One revision round only.
   - Done when: revised champion addresses every judge defect or logs why not.
5. **Verify and hand back.** Run the artifact (`/verify` discipline — render it, drive it) and
   return the tournament record. Code that ships goes through the normal merge-gate path.
   - Done when: champion observed working + record emitted.

## Output format

Return to the caller (and drop beside the artifact as `tournament-record.md`):
scores table (per criterion, per contestant), winner + rationale, defects fixed in revision,
grafts taken (from whom, what), and the champion's location.

## Calibration

- 3 contestants default; 5 max only when the brief names >3 truly distinct audiences/angles.
- Contestants run at medium effort — diversity + judge + revision recover depth (same doctrine
  as `output-tournament`). Judge and revision run at high effort.
- Live benchmark: contestant scores 91/93/92 — a spread under ~5 points is normal and does NOT
  mean the tournament failed; the revision round is the payoff.
- One revision round. A second tournament on the champion is scope creep — hand back instead.

## What this skill is NOT

- Not `output-tournament` — that competes short creative VARIANTS (copy, taglines, directions);
  this competes complete built artifacts with file output and worktree isolation.
- Not `boardroom`/`ceo-board` — those triangulate a decision; nothing is built.
- Not `opus-adversary` — that reviews ONE existing artifact; here generation itself competes.
- Not a substitute for loops — for iterative refinement of a known direction, loop instead
  (ranked above tournaments in the source's own testing).

## Hard rules

1. Contestants never see each other's work; the judge never sees personas. Contamination
   observed to collapse the diversity the pattern depends on.
2. The judge is never a contestant (builder≠reviewer — Anthropic engineer doctrine).
3. Synthesis is grafting into ONE coherent artifact — concatenation is the dominant naive
   failure.
4. Client-facing words inside the artifact still route through `nexus-copywriter`; the
   tournament does not bypass the estate content gate.
5. Declare rubric before generation. Post-hoc criteria let the judge rationalise a favourite.

## Provenance

- Source: Angela Jiang via Dream Labs live test — https://www.youtube.com/watch?v=PqlnPcae5OQ
- Vault: `Wiki/compete-mode-build-tournament-2026-07-15-ingest.md` (scores, ranking vs loops).
