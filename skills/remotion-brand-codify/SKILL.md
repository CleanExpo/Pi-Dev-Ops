---
name: remotion-brand-codify
description: Converts a BrandResearch dossier into a typed BrandConfig TypeScript file at Synthex/packages/brand-config/src/brands/{slug}.ts (canonical home per RA-1985 / Synthex SYN-897). Also emits a DESIGN.md projection at Pi-Dev-Ops/remotion-studio/src/brands/{slug}.md. Triggered after remotion-brand-research, or when the user pastes brand assets and says "codify". PRs are auto-merge:false — a human reviews before merge.
automation: automatic
intents: codify-brand, write-brand-config
---

# remotion-brand-codify

Turns research output into typed code that every composition reads.

## Triggers

- After `remotion-brand-research` writes a dossier under `.research/`.
- User pastes brand colours, fonts, and tone notes and says "codify the {brand} brand".

## Inputs

- `.research/brand-{slug}-{date}.json` (preferred) or the markdown dossier
- Existing `Synthex/packages/brand-config/src/brands/{slug}.ts` if present (for diff)

## Method

1. Validate the dossier covers every required field of `BrandConfig` (see `Synthex/packages/brand-config/src/types.ts`). Missing fields = block; ask `remotion-brand-research` to fill.
2. For each colour, run through `remotion-colour-family` if the palette has fewer than 5 colours or fails WCAG-AA on `text on primary`.
3. For motion, run through `remotion-motion-language` if `motion` block is empty.
4. For fonts, validate licensing: only OFL / Apache / MIT families pass. Block on Adobe Fonts (server-side rendering disallowed) and paid Google Fonts.
5. Emit `Synthex/packages/brand-config/src/brands/{slug}.ts` matching the existing template (see `Synthex/packages/brand-config/src/brands/ra.ts` for canonical example). Run `npm run build` from `Synthex/packages/brand-config/` afterwards to regenerate `dist/`.
6. Update `Synthex/packages/brand-config/src/brands/index.ts` if the slug is new (also extend `BrandSlug` union in `types.ts`).

## Output

Two edited files per brand:
1. `Synthex/packages/brand-config/src/brands/{slug}.ts` — typed `BrandConfig` (source of truth, per RA-1985).
2. `Pi-Dev-Ops/remotion-studio/src/brands/{slug}.md` — 9-section `DESIGN.md` projection following the open-design schema (vendored reference: `remotion-studio/src/design-systems/_library/`). The `.md` projection stays in Pi-CEO's remotion-studio; only the `.ts` source-of-truth migrated to Synthex.

The `.md` is a *projection* of the `.ts`, not a parallel source. Regenerate it whenever the `.ts` changes; never hand-edit. Section order is fixed:

1. Visual Theme & Atmosphere
2. Color Palette & Roles (table mirroring `BrandColour` slots, plus `darkVariant` row if defined)
3. Typography Rules (display / body / mono families, weights, line-heights)
4. Component Stylings (Primary CTA, Cards, plus any brand-specific component noted in `doNot`)
5. Layout Principles (grid, margins, logo placement from `BrandLogo.safeAreaPx`)
6. Depth & Elevation
7. Do's and Don'ts (concatenate `doNot` + `voice.forbiddenWords`)
8. Responsive Behavior (aspect ratios, type scale per ratio)
9. Agent Prompt Guide (one literal example invoking `colour.*` and `motion.signature` tokens)

Plus a PR (or local diff) summarising:
- Source dossier path
- Fields filled vs left to founder review
- Lint status (font licence, contrast)
- Both files emitted (`.ts` + `.md`) — block on missing `.md` projection

## Boundaries

- Always set PR `auto-merge:false` — brand voice nuance must be reviewed by a human.
- Never overwrite an existing file silently; produce a side-by-side diff.
- Never invent fonts or colours — values come from the research dossier or default to neutral fallbacks with `// TODO: founder review` comments.

## Reused utilities

- `Synthex/packages/brand-config/src/types.ts` — schema source of truth (per RA-1985)
- `remotion-studio/src/colour/index.ts` — `contrast()` for WCAG checks
- `remotion-studio/src/design-systems/_library/` — 138 vendored reference DESIGN.md files (open-design, Apache-2.0). Cite at most one as a visual-school anchor in the `.md` projection; never copy verbatim
- Reference projection: `remotion-studio/src/brands/ra.md` is the canonical example to mirror
