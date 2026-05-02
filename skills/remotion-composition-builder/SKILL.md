---
name: remotion-composition-builder
description: Authors or extends a Remotion composition (.tsx) wired to BrandConfig + Storyboard + layout spec + motion. The actual builder skill — runs as Sonnet 4.7 worker. Triggered after brand, storyboard, designer, and motion-language outputs are ready. Produces the file under remotion-studio/src/compositions/ and registers it in src/Root.tsx.
automation: automatic
intents: build-composition, write-composition, edit-composition
---

# remotion-composition-builder

The hands. Reads everything else, writes the TSX.

## Triggers

- Wave 4 of a `remotion-orchestrator` plan.
- User asks to "build a composition for {topic}" with brand + storyboard already known.

## Inputs

All consumed from prior skill outputs in the same job:
- `BrandConfig` (from `src/brands/{slug}.ts`)
- Storyboard JSON (from `remotion-screen-storyteller`)
- Layout spec (from `remotion-designer`)
- Motion block (already part of BrandConfig)
- Channel spec / aspect ratio (from `remotion-marketing-strategist`)

## Method

1. **Locate composition** — does `src/compositions/{Name}.tsx` exist?
   - If yes → patch in place (preserve existing API).
   - If no → create new file using `Explainer.tsx` as the template.
2. **Wire imports** — `import { brands } from '../brands'`, motion helpers from `../motion`, colour helpers from `../colour`.
3. **Define schema** — `z.object` for input props matching the Storyboard shape.
4. **Compose scenes** — one `<Sequence>` per storyboard scene. Each scene component reads `cfg = brands[props.brand]` and applies colour/typography/motion from `cfg`.
5. **Audio** — wire `<Audio src={staticFile(scene.voiceoverAudioPath)} />` per scene if path is set.
6. **Register in Root** — add or update `<Composition id="{Name}" ... />` in `src/Root.tsx`. `durationInFrames = sum(scene.durationSec) * fps`.
7. **File hygiene** — composition file ≤500 lines. Extract scenes to `src/compositions/{Name}/scenes/*.tsx` if it grows past that.
8. **Type check** — run `npx tsc --noEmit`. On red, fix and retry once.

## Output

Edited files:
- `src/compositions/{Name}.tsx` (or scene sub-files)
- `src/Root.tsx` (registry entry)

Status report to `remotion-orchestrator`:

```jsonc
{ "composition": "Explainer", "filesChanged": [...], "tscPassed": true, "ready": true }
```

## Boundaries

- Never inline brand values (hex codes, font names) — always read from `cfg`.
- Never set `durationInFrames` without summing storyboard scene durations × fps.
- Never `staticFile()` an asset path that doesn't exist — fail loud at build, not silent at render.
- Never bypass `signatureEntry()` for entry motion — keeps motion-language consistent.

## Reused

- [`src/compositions/Explainer.tsx`](../../remotion-studio/src/compositions/Explainer.tsx) — canonical template
- [`src/motion/index.ts`](../../remotion-studio/src/motion/index.ts) — `signatureEntry`, `brandFadeIn`, `staggerStart`
- [`src/colour/index.ts`](../../remotion-studio/src/colour/index.ts) — `readableOn`, `brandGradient`, `contrast`

## Hands off to

`remotion-render-pipeline` to actually render.
