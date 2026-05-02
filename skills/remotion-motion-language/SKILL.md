---
name: remotion-motion-language
description: Designs a brand-specific motion vocabulary — easing curves, default scene durations, signature entry/exit, transition frames. Each brand gets one signature move (rise / sweep / pulse / iris / whip) that recurs across compositions to build motion-recognition. Triggered when BrandConfig.motion is empty.
automation: automatic
intents: motion-language, signature-motion, easing, transitions
---

# remotion-motion-language

Owns "how the brand moves". Outputs a `BrandMotion` block, validated against `remotion-studio/src/motion/index.ts`.

## Triggers

- BrandConfig has no `motion` block, or `motion.signature` is unset.
- A composition feels generic — designer flags "needs distinctive motion".
- New composition type is added that needs to inherit brand motion.

## Inputs

- `brandSlug`
- Tone descriptors from `BrandConfig.voice.tone` (authoritative / urgent / warm / etc.)
- Audience from `BrandConfig.audience`

## Signature motion catalogue

| Signature | Best for | Bezier (in) | Anchor frame budget @ 30fps |
|---|---|---|---|
| `rise` | authoritative, reassuring (DR, NRPG) | `cubic-bezier(0.22, 1, 0.36, 1)` (expo-out) | base 22, slow 40 |
| `sweep` | expert, urgent, decisive (RA) | `cubic-bezier(0.22, 1, 0.36, 1)` | base 18, slow 36 |
| `iris` | pedagogical, focus-led (CARSI) | `cubic-bezier(0.83, 0, 0.17, 1)` (expo-in-out) | base 24, slow 42 |
| `pulse` | retail, energetic (CCW) | `cubic-bezier(0.34, 1.56, 0.64, 1)` (back-out) | base 14, slow 28 |
| `whip` | high-impact reveal | `cubic-bezier(0.36, 0, 0.66, -0.56)` (back-in) | base 12, slow 24 |

## Method

1. Map tone → signature (table above).
2. Set `durations.fast / base / slow` per signature row.
3. Set `transitionFrames` = round(durations.base × 0.7).
4. Set easing trio: `in` (expo-out by default), `out` (expo-in), `inOut` (expo-in-out).
5. Validate the signature is supported by [`signatureEntry()`](../../remotion-studio/src/motion/index.ts) — if not, fall back to `rise` and note in PR.

## Output

A `BrandMotion` object for direct insertion into `BrandConfig.motion`. Plus a 2-3 line rationale comment explaining why this signature was chosen for this brand.

## Boundaries

- Never use `pulse` (overshoot) for `authoritative` brands — feels frivolous.
- Never use `whip` for `reassuring` brands — too aggressive.
- Never extend the catalogue without also adding a case to `signatureEntry()` — runtime would fall through to identity.

## Hands off to

`remotion-brand-codify` writes the result; `remotion-composition-builder` reads it via `cfg.motion`.
