# RestoreAssist Design System

> Projection of `ra.ts`. Source of truth: `src/brands/ra.ts`. Do not hand-edit — regenerate via `remotion-brand-codify`.
> Tagline: *One National Inspection Standard.*

## 1. Visual Theme & Atmosphere

Restoration-clarity. Teal anchors the palette to convey clinical precision without sterility; lime accent signals NIR moments of action. Typography is pure Inter — no serifs, no flourish — paired with JetBrains Mono for inspection codes and timestamps. Cadence is short and decisive; voice is expert + urgent. The system reads more like a field-instrument readout than a marketing site.

## 2. Color Palette & Roles

| Role | Token | Hex |
|---|---|---|
| Primary | `colour.primary` | `#0E7C7B` (teal) |
| Secondary | `colour.secondary` | `#2A3D45` (slate) |
| Accent | `colour.accent` | `#C5E063` (lime — NIR highlight, CTAs) |
| Neutral 50 | `colour.neutral.50` | `#F5F7F8` |
| Neutral 100 | `colour.neutral.100` | `#E4E9EC` |
| Neutral 500 | `colour.neutral.500` | `#6F7B82` |
| Neutral 900 | `colour.neutral.900` | `#0E1518` |
| Success | `colour.semantic.success` | `#3FA34D` |
| Warning | `colour.semantic.warning` | `#E0A800` |
| Danger | `colour.semantic.danger` | `#C0392B` |
| Family | `colour.family` | `restoration` |

Dark variant: primary lifts to `#16B5B3`; neutrals invert (`50 ↔ 900`).

## 3. Typography Rules

- **Display**: Inter ExtraBold (800), `fonts/ra/Inter-ExtraBold.woff2`
- **Body**: Inter Regular (400)
- **Mono**: JetBrains Mono Medium (500) — inspection codes, timestamps, NIR identifiers only

Editorial pacing is rejected; cadence is short. Headline line-height tight (≤1.10), body relaxed (1.4–1.5), no italic for emphasis (use weight + colour).

## 4. Component Stylings

- **Primary CTA**: lime (`#C5E063`) on slate (`#2A3D45`) text; 8px radius.
- **Cards**: neutral.50 surface, 1px solid neutral.100 border, 12px radius.
- **Inputs**: slate underline (no full border), focus ring teal.
- **Mono chips** (NIR codes): JetBrains Mono on neutral.100, 6px radius.

## 5. Layout Principles

- 12-col grid, 96px outer margin (1920×1080) / 64px (1080×1920).
- Safe area 5% from each edge. Logo top-left, never centred.
- Maximum 3 colours per scene; lime reserved for accent only.

## 6. Depth & Elevation

- Flat surfaces preferred over drop shadows. Use 1px borders + tonal shifts.
- Elevation when needed: `0 4px 12px rgba(14,21,24,0.08)` (warm-tinted).
- Active states: invert background to slate, text to neutral.50.

## 7. Do's and Don'ts

**Do** (from `voice.tone` + `colour.family`):
- Lead with NIR data and field evidence — voice is *expert + urgent*.
- Reserve lime for action moments (CTAs, NIR call-outs).
- Use mono for any code, identifier, or timestamp.

**Don't** (from `doNot` + `voice.forbiddenWords`):
- Never abbreviate the company name to "RA" in voiceover or on-screen titles.
- Never use red as a primary brand colour (reserved for danger only).
- Never imply the NIR is optional or vendor-specific.
- Banned words: `we`, `our`, `i`, `us`, `my`, `leverage`, `utilise`, `best-in-class`.

## 8. Responsive Behavior

Aspect ratios supported: `1920×1080`, `1080×1920`, `1080×1080`. Hero type scales 96→64→48pt across landscape→square→portrait. Mono identifiers never wrap — clamp width or shrink scale instead.

## 9. Agent Prompt Guide

- **Voice**: expert + urgent, short cadence. Audience: restoration company owners and field technicians (AU); secondary insurer claims teams.
- **Default channel**: LinkedIn.
- **Voiceover**: ElevenLabs `EXAVITQu4vr4xnSDxMaL` (Sarah, AU/UK), narration style.
- **Signature motion**: `sweep` (horizontal reveal — decisive). Base 18 frames @ 30fps.
- Example prompt: *"Render an Explainer hero on `colour.primary` (#0E7C7B) with Inter ExtraBold 96pt headline in `neutral.50`. Place a `colour.accent` (#C5E063) chip with the NIR identifier in JetBrains Mono. Reveal with `signature: sweep` over 18 frames."*
