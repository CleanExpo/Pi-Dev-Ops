---
name: evidence-board
description: Answer a question or frame a decision with MULTIPLE evidence-backed viewpoints instead of a single verdict. Pulls multiple credible documentations via source-ingest (deliberately including disconfirming sources), then has Board persona lenses + a Senior Project Manager reason over the SAME cited corpus to produce a multi-vision brief — 2–4 distinct options, each with rationale, supporting AND opposing citations, confidence, and the lens that holds it — plus a Senior-PM synthesis (strongest-supported option, live tensions, what evidence would change the answer). Use when the user says "give me options / multiple viewpoints", "don't give a single answer", "what are the perspectives on", "multi-vision", "evidence-based options", "pressure-test with evidence", or any question where a one-sided answer would be misleading. Options-out sibling of ceo-board (which is decision-out). NOT for fiction.
---

# Evidence Board — multi-vision, evidence-grounded

The job is NOT to give *the* answer. It is to surface the real spectrum of defensible positions, each tied to evidence, so the decision is informed. Single-viewpoint output is the failure mode this skill exists to prevent.

## Hard rules
1. **Multi-source, multi-viewpoint — dissent fetched INDEPENDENTLY.** Never reason from one document. Gather **≥3 credible sources** via `source-ingest`, and DELIBERATELY seek **disconfirming / opposing** evidence. **Pull each dissent as its OWN separately-fetched source — never trust a confirming source's summary of the view that rebuts it** (a publisher framing its own critics softens the conflict). Verified in practice: a meta-analysis claimed "fear never backfires," but the independently-fetched rebuttal found a *net-negative* effect — the conflict only surfaced because the dissent was pulled on its own. If every source agrees, you haven't searched hard enough.
2. **Evidential intelligence.** Every claim a lens makes is tagged: `[evidence: <source>]` (cites a stored Tier-1/2 file), `[prior]` (reasoning, no source), or `[gap]` (no evidence found — flag it). No unmarked assertions.
3. **Options, not a verdict.** Output preserves 2–4 distinct positions. A recommendation is allowed, but framed as "strongest-supported given current evidence" alongside the live tension and the evidence that would flip it.
4. **Tier discipline** (from `source-ingest`): only Tier-1/2 anchors a fact; Tier-3 is context, traced back before use.

## Stage 1 — Senior PM frames (orchestrator)
The Senior Project Manager reads the question and emits:
- The real decision/question in one sentence.
- **The fault lines** — 2–4 dimensions where reasonable parties would DISAGREE (these become the viewpoints).
- 3–6 sharp empirical questions the evidence must answer (each ends in `?`).
Save as `brief.md`.

## Stage 2 — Evidence gathering (multi-source, via source-ingest)
Run `source-ingest` for each empirical question. Pull a CORPUS, not one hit: aim ≥3 credible sources spanning the fault lines, including the strongest source AGAINST the obvious answer. Each lands in the vault `Sources/` with credibility tier + citation. Compile a `evidence.md` index listing every source by ID, tier, and which fault line(s) it speaks to. If a fault line has no evidence, mark it `[gap]` — do not paper over it.

## Stage 3 — Parallel lenses over the SAME corpus
Dispatch parallel sub-agents (see `parallel-delegate`), one per Board lens relevant to the question — draw from `ceo-board` personas: **Contrarian** (mandatory — steelmans the opposing view), **Technical Architect**, **Market Strategist**, **Revenue/Compounder**, **Custom Oracle** (domain expert), and any fault-line-specific lens. Each lens:
- reads the shared `evidence.md` corpus (not its priors first),
- argues its position, citing specific sources by ID with the `[evidence:]/[prior]/[gap]` tags,
- names what evidence would change its mind.
Each returns a structured position (stance, key citations for, key citations against, confidence).

## Stage 4 — Senior PM synthesis → multi-vision brief
The Senior PM does NOT pick a winner and bury the rest. It produces `multi-vision.md`:
1. **Question** + fault lines.
2. **Evidence base** — the cited corpus (source IDs, tiers, links).
3. **The options (2–4)** — for each: the position; who holds it (which lens); the rationale; **citations FOR**; **citations AGAINST**; confidence (high/med/low) and why.
4. **Tensions** — where the evidence genuinely conflicts or is thin.
5. **Senior-PM recommendation** — the strongest-supported option *as of this evidence*, explicitly NOT the only one, with the tradeoff accepted and **"what would change this"** (the finding that would flip the recommendation).
6. **Confidence + gaps** — overall confidence and the `[gap]` items worth resolving next.

## Output
`multi-vision.md` (+ `brief.md`, `evidence.md`) in the working folder; store a copy in the vault `Decisions/` if it informs a ratified call. Every viewpoint must trace to the evidence base. Hand to `ceo-board` only if the user then wants the options collapsed into ONE ratified decision.

## Composition
`source-ingest` (evidence) → this skill (multi-vision options) → optionally `ceo-board` (decision-out). Reuses ceo-board persona definitions (`ceo-board/references/board-members.md`).
