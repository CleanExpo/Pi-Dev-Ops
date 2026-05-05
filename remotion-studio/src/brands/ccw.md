# Carpet Cleaners Warehouse (CCW) Design System

> Projection of `ccw.ts`. Source of truth: `src/brands/ccw.ts`. Do not hand-edit — regenerate via `remotion-brand-codify`.
> Tagline: *Trade prices. Same-day dispatch.*

## 1. Visual Theme & Atmosphere

Warm + urgent — the only consumer brand in the umbrella. Bold red primary with deep-blue secondary and orange accent reads like trade retail signage: high-energy, instantly recognisable, no apology for being commercial. Outfit ExtraBold display delivers retail punch; Inter body keeps prices scannable. Motion uses overshoot easing — products land like they're being slammed onto a counter.

## 2. Color Palette & Roles

| Role | Token | Hex |
|---|---|---|
| Primary | `colour.primary` | `#D62828` (retail red) |
| Secondary | `colour.secondary` | `#003049` (deep blue) |
| Accent | `colour.accent` | `#F77F00` (orange) |
| Neutral 50 | `colour.neutral.50` | `#FFFFFF` |
| Neutral 100 | `colour.neutral.100` | `#F5F5F5` |
| Neutral 500 | `colour.neutral.500` | `#737373` |
| Neutral 900 | `colour.neutral.900` | `#1A1A1A` |
| Success | `colour.semantic.success` | `#3FA34D` |
| Warning | `colour.semantic.warning` | `#E0A800` |
| Danger | `colour.semantic.danger` | `#7B0F0F` (deepened — primary already red) |
| Family | `colour.family` | `consumer` |

CCW is the only brand where red can be primary (`family === 'consumer'` exception).

## 3. Typography Rules

- **Display**: Outfit ExtraBold (800) — modern geometric sans, retail energy
- **Body**: Inter Regular (400)
- No mono.

Display tight (1.05); body 1.4. Prices always in display weight, never body.

## 4. Component Stylings

- **Hero CTA**: red on white text; 8px radius. Single hero CTA per scene.
- **Price chip**: orange background, deep-blue text, 6px radius.
- **Product card**: white surface, 1px solid neutral.100, 12px radius.

## 5. Layout Principles

- 12-col, 64px outer margin (less breathing room — retail density).
- Product imagery dominates the frame (60%+); copy supports it.
- Logo bottom-right, safe area 32px (smaller than other brands — fits retail furniture).

## 6. Depth & Elevation

- Pop shadows on product cards: `0 8px 24px rgba(0,48,73,0.12)` (deep-blue tinted).
- Hero CTA: `0 4px 12px rgba(214,40,40,0.30)` — confident lift.

## 7. Do's and Don'ts

**Do**:
- Lead with the price or the dispatch promise.
- Use orange for price chips; reserve red for hero/CTA only.

**Don't**:
- Never claim products are "the cheapest" — use "trade pricing" instead.
- Never use red type on coloured backgrounds (reserve red for hero/CTA).
- Banned words: `we`, `our`, `i`, `us`, `my`, `cheap`, `discounted`.

## 8. Responsive Behavior

Aspect ratios: prefers `1080×1920` (Instagram first). Display Outfit 96→72→56pt. Product hero scales but never crops below 60% of frame.

## 9. Agent Prompt Guide

- **Voice**: warm + urgent, short cadence. Audience: professional carpet cleaners and restoration trades (AU).
- **Default channel**: Instagram.
- **Voiceover**: `EXAVITQu4vr4xnSDxMaL`, conversational, en-AU.
- **Signature motion**: `pulse` (overshoot bounce — retail energy). Base 14 frames @ 30fps. Easing uses overshoot curve `cubic-bezier(0.34, 1.56, 0.64, 1)`.
- Example prompt: *"Vertical 1080×1920. Hero on white. Product slams in via `signature: pulse` with overshoot easing, 14 frames. Price chip in orange (#F77F00) with deep-blue (#003049) text. Single CTA in red (#D62828) at the bottom safe area."*
