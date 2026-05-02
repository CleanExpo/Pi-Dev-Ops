---
name: remotion-brand-codify
description: Converts a BrandResearch dossier into a typed BrandConfig TypeScript file at remotion-studio/src/brands/{slug}.ts. Triggered after remotion-brand-research, or when the user pastes brand assets and says "codify". PRs are auto-merge:false — a human reviews before merge.
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
- Existing `src/brands/{slug}.ts` if present (for diff)

## Method

1. Validate the dossier covers every required field of `BrandConfig` (see `remotion-studio/src/brands/types.ts`). Missing fields = block; ask `remotion-brand-research` to fill.
2. For each colour, run through `remotion-colour-family` if the palette has fewer than 5 colours or fails WCAG-AA on `text on primary`.
3. For motion, run through `remotion-motion-language` if `motion` block is empty.
4. For fonts, validate licensing: only OFL / Apache / MIT families pass. Block on Adobe Fonts (server-side rendering disallowed) and paid Google Fonts.
5. Emit `src/brands/{slug}.ts` matching the existing template (see `src/brands/ra.ts` for canonical example).
6. Update `src/brands/index.ts` if the slug is new.

## Output

A single edited file: `remotion-studio/src/brands/{slug}.ts`. Plus a PR (or local diff) summarising:
- Source dossier path
- Fields filled vs left to founder review
- Lint status (font licence, contrast)

## Boundaries

- Always set PR `auto-merge:false` — brand voice nuance must be reviewed by a human.
- Never overwrite an existing file silently; produce a side-by-side diff.
- Never invent fonts or colours — values come from the research dossier or default to neutral fallbacks with `// TODO: founder review` comments.

## Reused utilities

- `remotion-studio/src/brands/types.ts` — schema source of truth
- `remotion-studio/src/colour/index.ts` — `contrast()` for WCAG checks
