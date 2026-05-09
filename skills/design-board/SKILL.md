---
name: design-board
description: Five-persona deliberation skill for brand design — 15+ years of typography, layout, colour, motion, and 3D expertise. Five subagents (Art Director, Brand Systems Architect, Motion Designer, WebGL/3D Specialist, Critic) propose, cross-examine, and synthesise N concrete variants of a brand visual identity. Each variant is a complete `.design.md` + `.motion.md` (+ optional `.scene.md`) that the design-iterate loop hands back to the client (the user) for review. Triggered by `design-iterate`, or directly when the user says "convene the design board for {brand/brief}".
automation: manual
intents: design-board, brand-design, design-deliberation, generate-variants, visual-identity-board
---

# design-board

Five-persona brand-design deliberation. Modelled on `~/.claude/skills/ceo-board/` but for visual identity. Each persona contributes one lens; the Critic vetoes weak proposals before they reach the client; the Architect synthesises survivors into N concrete variants.

## Triggers

- `design-iterate` calls in a loop while the user is refining a brand.
- User says "convene the design board for {brief}", "generate 3 design variants for {brand}", "I want fresh design directions for {brand}".
- After `remotion-brand-research` completes the dossier for a NEW brand and before `remotion-brand-codify` writes any tokens.

## Inputs

- `brief` — free-text design brief OR path to a `remotion-brand-research` dossier
- `slug` — brand slug (existing or new)
- `variantCount` (default 3) — how many concrete variants to synthesise
- `iteration` (default 1) — which round of the iterate loop this is
- `notes` (optional) — feedback from the previous iteration's user review
- `forbid` (optional) — list of design directions the user has explicitly ruled out
- `family` (optional) — colour family enum if known; the Brand Systems Architect uses it for cross-brand coherence

## Method

Three rounds, persona definitions in [`references/personas.md`](references/personas.md). Each persona is a Sonnet 4.6 subagent (Critic is Opus 4.7).

### Round 1 — Propose

Each persona reads the brief + any prior-iteration notes and emits a position paper:

- Art Director — typography hierarchy, layout system, white-space philosophy, visual school anchor (cite ONE from `Pi-Dev-Ops/remotion-studio/src/design-systems/_library/`)
- Brand Systems Architect — token coherence with existing portfolio, family rules to inherit, what to deliberately diverge on
- Motion Designer — signature choice (rise/sweep/iris/pulse/whip), easing semantics, choreography sketch, reduced-motion plan
- WebGL/3D Specialist — *only if 3D is warranted by the brief*; otherwise emits "skip — flat is right for this brand"
- Critic (Opus) — adversarial pre-read: pressure-test the brief itself for hidden assumptions, "AI-default" patterns, generic-SaaS pitfalls

Round 1 outputs land in `.research/design/iterations/{slug}-{iteration}/round-1/{persona}.md`.

### Round 2 — Cross-examine

Each non-Critic persona reads the other Round 1 papers and emits a 1-page "where I disagree" memo. The Critic reads everything and emits a "what is generic / what is borrowed / what is earned" verdict for each Round 1 paper, with a per-paper KEEP / FIX / KILL tag.

Round 2 outputs land in `.research/design/iterations/{slug}-{iteration}/round-2/{persona}.md`.

### Round 3 — Synthesise into variants

The Brand Systems Architect (acting as chair) takes the Round 2 verdicts and drafts `variantCount` concrete variants. Each variant is a full triple:

- `variant-{n}.design.md` — spec-conformant `@google/design.md`
- `variant-{n}.motion.md` — spec-conformant motion tokens (validates against the loadMotion zod schema)
- `variant-{n}.scene.md` — optional, only when WebGL/3D Specialist proposed it
- `variant-{n}.rationale.md` — why this variant, citing the personas + the visual-school anchor

Variants land in `.research/design/iterations/{slug}-{iteration}/`.

The Critic runs a final pass on all variants together: scores each on the 5-D rubric (Philosophy / Hierarchy / Detail / Functionality / Distinctiveness, each 0–10) and writes `variants-summary.md` listing the top variants in score order with one-line "school" labels (e.g. "Stripe-precision-with-restoration-warmth").

## Output

```
.research/design/iterations/{slug}-{iteration}/
├── round-1/{art-director,architect,motion,webgl,critic}.md
├── round-2/{art-director,architect,motion,webgl,critic}.md
├── variant-1.design.md
├── variant-1.motion.md
├── variant-1.scene.md          # optional
├── variant-1.rationale.md
├── variant-2.design.md
├── variant-2.motion.md
├── variant-2.rationale.md
├── variant-3.design.md
├── variant-3.motion.md
├── variant-3.rationale.md
└── variants-summary.md
```

Each `.design.md` lints clean against `@google/design.md lint`; each `.motion.md` parses against `MotionTokensSchema` (loadMotion); each optional `.scene.md` parses against `SceneTokensSchema` (loadScene). The `design-iterate` loop driver runs these validators before showing the variants to the user.

## Boundaries

- **Never present a variant the Critic tagged KILL.** Generate a replacement first.
- **Never duplicate tokens across `.design.md` and `.motion.md`.** Per `Pi-Dev-Ops/remotion-studio/src/brands/CONTRACT.md`.
- **Never invent fonts the brand can't license.** OFL / Apache / MIT only — same rule as `remotion-brand-codify`.
- **Never produce a variant without citing one of the 140 visual schools.** Anchor to a real reference; don't float in the AI-default void.
- **Never skip the WebGL Specialist's "skip — flat is right" verdict.** Most brands don't need 3D; honouring "skip" is a feature.

## Reused

- `~/.claude/skills/ceo-board/references/board-members.md` — persona definition template (Model / Role / Worldview / Move / Blindspot / Voice)
- `~/.claude/skills/opus-adversary/SKILL.md` — used directly for the Critic's adversarial pass
- `Pi-Dev-Ops/remotion-studio/src/design-systems/_library/` — 140 visual-school anchors; Art Director MUST cite one
- `Pi-Dev-Ops/remotion-studio/src/brands/CONTRACT.md` — token boundary
- `Pi-Dev-Ops/remotion-studio/src/brands/loadMotion.ts` + `loadScene.ts` — schemas for motion + scene
- `~/.claude/skills/aura/SKILL.md` — index of vendored Aura skills (GSAP, Three.js, Animation Systems, Frontend Design Distinctive) the personas can cite

## Hands off to

`design-iterate` consumes the variant set + summary, renders them via `design-canvas-html` and the preview-canvas, and presents to the user.
