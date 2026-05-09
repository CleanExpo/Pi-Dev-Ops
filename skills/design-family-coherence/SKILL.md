---
name: design-family-coherence
description: Cross-brand audit. Given a colour family (`restoration | safety | industrial | consumer | training`), reads every brand's `.design.md` + `.motion.md` and reports on family-level consistency — shared signature motion, shared spacing rhythm, shared typography weight ladder, palette saturation curve. Flags drift. Used after `design-approve` adds a new brand to the family, and as a standing monthly audit.
automation: manual
intents: design-family-coherence, brand-family-audit, cross-brand-consistency, family-drift-check
---

# design-family-coherence

The portfolio-level lens. Treats each `ColourFamily` as a system whose members should READ as related without being identical.

## Triggers

- `design-approve` calls automatically after a new brand is added to a family.
- User says "audit the safety family", "are DR and NRPG visually coherent?", "check family drift".
- Standing monthly task (per the orchestrator).

## Inputs

- `family` — `restoration | safety | industrial | consumer | training`
- `strict` (default false) — strict mode requires unanimous shared signature; lax mode allows justified divergence

## Method

1. **List members**: read every brand `.ts` whose `colour.family` matches the input. (Map currently maintained at `Pi-Dev-Ops/preview-canvas/app/family/[familyName]/page.tsx:FAMILY_OF`.)

2. **Load each brand's three specs**: `loadDesign`, `tryLoadMotion`, `tryLoadScene`.

3. **Run coherence checks**:

   | Check | What it tests | Pass criterion |
   |---|---|---|
   | Signature motion | All `.motion.md` `signature.name` agree | `strict`: all equal · `lax`: ≥2/3 majority |
   | Display typeface | All `.design.md` `typography.display-*.fontFamily` share family | All equal |
   | Spacing rhythm | All `.design.md` `spacing.md` values share base ratio (e.g. all 16, all 4 / 8 / 16 / 32 / 64 doubling) | All match base |
   | Saturation curve | All `colors.primary` OKLch chroma within ±0.02 | Within band |
   | Easing inheritance | All `motion.easings` share at least the `expo-out` (or family default) curve | Shared default curve present |
   | Component recipe parity | All brands define the same baseline components (cta-primary, card) | All present |
   | Motion budget | All `motion.durations.base` within ±20% | Within band |
   | Reduced-motion policy | All `motion.performance.prefersReducedMotion` agree | All equal |

4. **Emit a report**:

   ```
   .research/design/coherence/{family}-{YYYY-MM-DD}.md
   ```

   Each check gets a one-liner with ✓ / ⚠ / ✗ and citation:

   ```markdown
   # safety family coherence — 2026-05-07

   Members: dr, nrpg

   ✓ signature motion: both `rise`
   ✓ display typeface: both Inter
   ✗ spacing rhythm: dr uses 16/24/48 (3-step); nrpg uses 16/24/32/48 (4-step) — drift
   ⚠ saturation curve: dr.primary chroma 0.18; nrpg.primary chroma 0.12 — borderline
   ✓ easing inheritance: both define expo-out
   ✓ component recipe parity: both define cta-primary + card
   ✓ motion budget: dr base 22f, nrpg base 22f
   ✓ reduced-motion policy: both `respect`

   Verdict: PASS WITH NOTES. Resolve spacing drift before next brand joins.
   ```

5. **If verdict is BLOCK** (any ✗ check), open a Linear ticket `pi:design-coherence-{family}-{date}` with the report attached and assign to the founder.

6. **Surface in the canvas**: write a JSON sidecar `coherence-{family}.json` that the `/family/[familyName]` route can render inline.

## Output

Markdown report + optional Linear ticket. The canvas `/family/[familyName]` route picks up the JSON sidecar and shows ✓/⚠/✗ inline.

## Boundaries

- **Never auto-fix drift.** This skill audits only. Fixing requires a fresh `design-iterate` for the offending brand.
- **Never block on `consumer` or `training` family** today — they have <2 members so coherence is moot.
- **Never enforce strict mode without user opt-in.** Lax is the default; strict only on request.

## Reused

- `Pi-Dev-Ops/remotion-studio/src/brands/loadDesign.ts` / `loadMotion.ts` / `loadScene.ts`
- `Synthex/packages/brand-config/src/types.ts` — `ColourFamily` enum + `BrandConfig.colour.family`
- `Pi-Dev-Ops/preview-canvas/app/family/[familyName]/page.tsx` — visual surface

## Hands off to

The user (with the report) and Linear (with the ticket if BLOCK).
