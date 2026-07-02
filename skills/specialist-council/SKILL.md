---
name: specialist-council
description: AI Communication Intelligence layer — the bidirectional cross-specialist consultation protocol that makes specialist agents TALK TO EACH OTHER before an artifact is finalized. Use when a task spans domains and the output needs input from multiple specialists (e.g. marketing copy that must satisfy SEO + GEO + E-E-A-T + brand voice, or a video that needs Remotion + HeyGen + design + brand). Any orchestrator or /spm invokes it to pull structured input from the RIGHT specialists and fold it back in. Triggers on "AI communication intelligence", "agents talking to each other", "cross-specialist", "specialists should consult each other", "get input from all relevant specialists", "council". NOT a builder and NOT a replacement for the single-domain orchestrators — it is the round-trip consultation they lack.
---

# specialist-council — AI Communication Intelligence

The Pi substrate already dispatches agents (dispatcher-core), runs single-domain
production teams (marketing-orchestrator, video-director), debates one corpus
(ceo-board, evidence-board), and gates output (opus-adversary, brand-guardian).
What it lacks: **any specialist actively pulling structured input from a
DIFFERENT-domain specialist and integrating it before emitting.** Hand-off today
is one-way, upstream→downstream, via file artifacts. This skill adds the missing
**round-trip** — the intelligence layer for agent-to-agent communication.

**Core principle:** specialists *advise*; the artifact's owner *decides*. The
council gathers cross-domain input on a shared draft, folds it back, and bounds
the loop. It never produces the artifact itself.

## When to use
- A task whose quality depends on more than one specialist domain (content that
  must satisfy SEO + GEO + E-E-A-T + brand; a landing page; a video; a campaign).
- Inside an orchestrator's plan as a **"wave 0: consult"** step, or inside `/spm`
  as the specialist-board's cross-domain pass.

## When NOT to use
- Single-domain work (a pure SEO audit → just call `seo`). No council overhead.
- As a build step — it critiques and enriches; it does not generate the deliverable.
- Replacing the single-domain orchestrators — it composes WITH them.

## The protocol

### 1. Frame
Write the task + the current draft artifact to a shared file
(`council/{job_id}/draft.md` + `task.md`). This shared corpus is what every
specialist reasons over — reuse the `evidence-board` "N lenses over one corpus"
primitive.

### 2. Route (which specialists to consult)
Pick from the routing table below by task type. Only pull specialists whose input
would actually change the output — irrelevant consults are noise.

| Task type | Consult (parallel) |
|---|---|
| Content / copy / blog / landing page | `seo`, `geo-optimization`, `eeat` (E-E-A-T), `brand-guardian` |
| Campaign / GTM / launch | `marketing-orchestrator` (owner), `seo`, `geo-optimization`, `eeat` |
| Video / explainer / reel | `video-director` (owner), `heygen-director`, `remotion-designer`, `brand-guardian` |
| Static / social visual — incl. "Canva"-class graphics, carousels, thumbnails, one-pagers | `remotion-designer` + `design-board` / `design-canvas-html` (layout), `margot image_generate` (imagery), `brand-guardian` — our-stack substitute for Canva; no new tool |
| Any client-facing FACT claim | `source-ingest`, `eeat`, `brand-guardian` |

(Specialists marked "owner" produce; the rest consult. Add `opus-adversary` as a
final adversarial gate for high-stakes output.)

### 3. Fan out (the communication step)
Dispatch the consult specialists **in parallel** via `parallel-delegate`
(independent, over the same shared draft). Each is asked the SAME question:
*"Review this draft through your domain lens. Return structured input."* Each
returns a **consult response** (schema below) — never prose the owner has to parse.

**Coordination mode (name it per task).** Decision-grade / client-facing
artifacts use **centralized** synthesis — the owner or `/spm` gathers all consult
responses and integrates (high-bandwidth, one decision-maker). Reserve loose,
independent fan-out (no synthesis round) for cheap, genuinely separable subtasks.
Per DeepMind *"From AGI to ASI"* (arXiv:2606.12683, Pathway 4), centralized
high-bandwidth coordination is what lets a specialist collective exceed any single
agent; don't default to loose fan-out for work that needs a coherent result.

### 4. Synthesize + fold back
Merge the consult responses. Resolve conflicts explicitly (note disagreements,
don't silently pick). Apply every `must_fix`; fold in `suggestions` where they
don't conflict with the owner's intent. Record what was applied vs deferred.

### 5. Bounded re-consult
If applying the fixes materially changed the artifact AND any `must_fix` remains
open, run ONE more round over the same specialists (mirrors `opus-adversary`'s
single loop-back). Never loop unbounded — kill-switch aware (`~/.claude/HARD_STOP`).

### 6. Emit
Return the enriched artifact + a `consultation-record.json` (who was consulted,
their must_fix/suggestions, what was applied). The owner ships the artifact.

## Consult-response contract (structured hand-off)
Every consulted specialist returns exactly this — the shared language of the
communication layer:
```json
{
  "specialist": "geo-optimization",
  "verdict": "pass | needs-work | fail",
  "must_fix": [{"issue": "no llms.txt / citable answer block", "why": "invisible to AI Overviews", "evidence": "geo-optimization §Trust"}],
  "suggestions": [{"change": "add an FAQ answer block for the head query", "impact": "high"}],
  "confidence": 0.0
}
```

## Guardrails
- **Bounded:** max 2 consult rounds; parallel fan-out capped (parallel-delegate limits); kill-switch honored.
- **Relevance over volume:** consult only specialists whose input changes the output.
- **Diversity over redundancy:** collective gain comes from *specialization diversity*, not N copies of the same reviewer — roster genuinely distinct domain lenses and include at least one deliberately disconfirming one (DeepMind arXiv:2606.12683: collective intelligence depends on "diversity due to specialization"; mirrors the `evidence-board` opposing-source rule).
- **Cooperation gate (anti-"solipsism"):** each consulted specialist must cite and address at least one PEER's objection before its input is accepted — isolated, non-cooperative optimization is rejected. The paper names "solipsistic superintelligence" (agents optimizing in isolation) as the core failure mode; cooperation is a gate here, not a nicety. This is the council's oversight layer.
- **Advise ≠ decide:** the owner integrates; the council never overrides intent silently — conflicts are surfaced.
- **Autonomy ladder:** bounded single-domain consults run un-gated; cross-domain "group agent" strategic output (the ASI-shaped work) routes through human/Board review before shipping — maps to the existing policy-gate concern that multi-move execution is otherwise unguarded (see `pi-dev-ops-autonomy-gate-layer`).
- **No new tools:** consult only existing skills. The design/"Canva" lens is RESOLVED by substitution — Canva-class requests map to `remotion-designer` + `design-board` / `design-canvas-html` (layout) + `margot image_generate` (imagery), gated by `brand-guardian` (per `feedback-skool-substitute-our-stack`: install nothing new). E-E-A-T exists as `eeat`. Nothing stubbed here.

## Integration
- **Orchestrators:** add a `wave 0: consult` entry to the wave-plan/production-brief
  before production waves, invoking this skill on the brief.
- **/spm:** the specialist-board's cross-domain pass calls this to get real
  specialist input into the spec, not just persona role-play.
- **dispatcher-core:** expose as a `skill.specialist-council` step type.

## Anti-duplication
Builds ON `evidence-board` (shared corpus), `parallel-delegate` (fan-out),
`dispatcher-core` (dispatch), `opus-adversary` (loop-back). Does NOT replace the
single-domain orchestrators, the board (decision-out), or the gates. It is the
connective tissue between them — the enhance, not the rebuild.
