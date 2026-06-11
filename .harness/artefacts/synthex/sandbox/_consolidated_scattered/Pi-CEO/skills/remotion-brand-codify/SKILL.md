---
name: remotion-brand-codify
description: Converts a BrandResearch dossier into THREE artifacts — (1) typed BrandConfig TypeScript at Synthex/packages/brand-config/src/brands/{slug}.ts (runtime/behaviour: voice, voiceover, motion, audience, channel, forbiddenWords); (2) spec-conformant {slug}.design.md at Synthex/packages/brand-config/src/brands/{slug}.design.md (visual tokens: colour, typography, spacing, components, layout, elevation); (3) human-readable 9-section .md projection at Pi-Dev-Ops/remotion-studio/src/brands/{slug}.md derived from BOTH. Boundary contract at Pi-Dev-Ops/remotion-studio/src/brands/CONTRACT.md. Triggered after remotion-brand-research, or when the user pastes brand assets and says "codify". PRs are auto-merge:false — a human reviews before merge.
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
2. **Apply the boundary contract** — colour hexes / typography scale / spacing / components / layout go to `.design.md`; voice / voiceover / motion / audience / channel / forbiddenWords / logo paths / signature go to `.ts`. See `Pi-Dev-Ops/remotion-studio/src/brands/CONTRACT.md`.
3. For each colour, run through `remotion-colour-family` if the palette has fewer than 5 colours or fails WCAG-AA on `text on primary`. The colour-family skill emits a YAML block ready to drop into the `.design.md` `colors:` section.
4. For motion, run through `remotion-motion-language` if `motion` block is empty.
5. For fonts, validate licensing: only OFL / Apache / MIT families pass. Block on Adobe Fonts (server-side rendering disallowed) and paid Google Fonts.
6. Emit `Synthex/packages/brand-config/src/brands/{slug}.ts` containing **runtime fields only** (per CONTRACT.md). Use `Synthex/packages/brand-config/src/brands/ra.ts` as the canonical example. Run `npm run build` from `Synthex/packages/brand-config/` afterwards to regenerate `dist/`.
7. Emit `Synthex/packages/brand-config/src/brands/{slug}.design.md` containing **visual tokens only** in spec-conformant `@google/design.md` format. Use any existing `*.design.md` (e.g. `ra.design.md`) as the canonical example.
8. **Lint the design.md** — run `npx --prefix Pi-Dev-Ops/remotion-studio design.md lint Synthex/packages/brand-config/src/brands/{slug}.design.md`. Block on errors. Warnings are advisory — fix unreferenced-token warnings only when the unused token has no semantic intent.
9. **Mirror to the runtime location** — `cp Synthex/packages/brand-config/src/brands/{slug}.design.md Pi-Dev-Ops/packages/brand-config/src/brands/{slug}.design.md`. The runtime loader (`loadDesign(slug)`) reads from the Pi-Dev-Ops local copy via the workspace-link in remotion-studio.
10. Update `Synthex/packages/brand-config/src/brands/index.ts` if the slug is new (also extend `BrandSlug` union in `types.ts`).
11. Regenerate the human-readable 9-section projection at `Pi-Dev-Ops/remotion-studio/src/brands/{slug}.md` reading from BOTH `.ts` and `.design.md`. Sections 2 (Color Palette), 3 (Typography), 4 (Components), 5 (Layout) pull from `.design.md`; sections 1, 6, 7, 8, 9 pull from `.ts` + supporting prose.

## Output

Three edited files per brand:
1. `Synthex/packages/brand-config/src/brands/{slug}.ts` — typed `BrandConfig` (runtime + behaviour, source of truth per RA-1985).
2. `Synthex/packages/brand-config/src/brands/{slug}.design.md` — visual tokens (source of truth, spec-conformant `@google/design.md`).
3. `Pi-Dev-Ops/remotion-studio/src/brands/{slug}.md` — 9-section human-readable projection (regenerated from BOTH; never hand-edit).

Plus the runtime mirror at `Pi-Dev-Ops/packages/brand-config/src/brands/{slug}.design.md` (a cp of #2 — kept in sync until the brand-config consolidation removes the local copy).

The 9-section `.md` projection is a *projection* of the `.ts` + `.design.md`, not a parallel source. Regenerate it whenever either source changes; never hand-edit. Section order is fixed:

1. Visual Theme & Atmosphere (from `.ts` voice + audience prose)
2. Color Palette & Roles (table mirroring `.design.md` `colors:`, plus dark variant row if defined)
3. Typography Rules (from `.design.md` `typography:` + family/weight from `BrandTypography` for licence trace)
4. Component Stylings (from `.design.md` `components:`)
5. Layout Principles (from `.design.md` `spacing.outer-margin-*` + `BrandLogo.safeAreaPx`)
6. Depth & Elevation (from `.design.md` Elevation prose)
7. Do's and Don'ts (concatenate `.ts` `doNot` + `voice.forbiddenWords` + `.design.md` Do's/Don'ts section)
8. Responsive Behavior (aspect ratios from `.ts`, type scale per ratio from `.design.md`)
9. Agent Prompt Guide (one literal example invoking `{colors.*}` and `motion.signature` tokens)

Plus a PR (or local diff) summarising:
- Source dossier path
- Fields filled vs left to founder review
- Lint status (`design.md lint` errors / warnings, font licence, contrast)
- All three files emitted (`.ts` + `.design.md` + `.md` projection) — block on missing artifact

## Boundaries

- Always set PR `auto-merge:false` — brand voice nuance must be reviewed by a human.
- Never overwrite an existing file silently; produce a side-by-side diff.
- Never invent fonts or colours — values come from the research dossier or default to neutral fallbacks with `// TODO: founder review` comments.
- **Never duplicate a token across `.ts` and `.design.md`.** If `colour.primary` lives in `.design.md`, the `.ts` must not redeclare it. The CONTRACT.md is the arbiter.
- **Never edit the `.md` projection by hand** — regenerate from sources.

## Reused

- [`src/brands/CONTRACT.md`](../../remotion-studio/src/brands/CONTRACT.md) — token ownership boundary
- [`src/brands/ra.design.md`](../../packages/brand-config/src/brands/ra.design.md) — canonical `.design.md` example
- [`Synthex/packages/brand-config/src/brands/ra.ts`](../../../../Synthex/packages/brand-config/src/brands/ra.ts) — canonical `.ts` example
- [`src/design-systems/_library/`](../../remotion-studio/src/design-systems/_library/) — 140 vendored DESIGN.md files for visual-school anchoring (cite at most one)

## Reused utilities

- `Synthex/packages/brand-config/src/types.ts` — schema source of truth (per RA-1985)
- `remotion-studio/src/colour/index.ts` — `contrast()` for WCAG checks
- `remotion-studio/src/design-systems/_library/` — 138 vendored reference DESIGN.md files (open-design, Apache-2.0). Cite at most one as a visual-school anchor in the `.md` projection; never copy verbatim
- Reference projection: `remotion-studio/src/brands/ra.md` is the canonical example to mirror
