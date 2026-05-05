# NRPG Design System

> Projection of `nrpg.ts`. Source of truth: `src/brands/nrpg.ts`. Do not hand-edit — regenerate via `remotion-brand-codify`.
> Tagline: *Standards for the response network.*

## 1. Visual Theme & Atmosphere

Authoritative + expert. Slightly warmer navy than DR (the sister brand), softened by an aged-paper neutral and an amber accent that recalls a brass plaque. NRPG is an industry standard, not a regulator — the system reads more *institutional* than *operational*: think trade-body literature, not field manual.

## 2. Color Palette & Roles

| Role | Token | Hex |
|---|---|---|
| Primary | `colour.primary` | `#1A2A4F` (navy, warm) |
| Secondary | `colour.secondary` | `#2A3D5F` |
| Accent | `colour.accent` | `#F2B33D` (amber, brass) |
| Neutral 50 | `colour.neutral.50` | `#FAF8F2` (aged paper) |
| Neutral 100 | `colour.neutral.100` | `#EDE7D6` |
| Neutral 500 | `colour.neutral.500` | `#7A7468` |
| Neutral 900 | `colour.neutral.900` | `#0F1626` |
| Success | `colour.semantic.success` | `#3FA34D` |
| Warning | `colour.semantic.warning` | `#E0A800` |
| Danger | `colour.semantic.danger` | `#C0392B` |
| Family | `colour.family` | `safety` |

## 3. Typography Rules

- **Display**: Inter ExtraBold (800)
- **Body**: Inter Regular (400)
- No mono.

Headlines 1.10 line-height; body 1.5. Use letter-spacing 0.08em on all-caps section labels (institutional cue).

## 4. Component Stylings

- **Primary CTA**: navy on amber chip; 8px radius.
- **Cards**: aged-paper neutral.50 surface, 1px solid neutral.100 border.
- **Standards plaque**: navy header strip with amber underline; body in dark navy on neutral.50.

## 5. Layout Principles

- 12-col, 96px / 64px margins.
- Headlines centred when announcing standards; left-aligned for body content.
- Logo top-left, always with safe area = 48px.

## 6. Depth & Elevation

- Flat surfaces with hairline neutral.100 borders.
- Elevation only on the standards-plaque component: `0 4px 16px rgba(15,22,38,0.10)`.

## 7. Do's and Don'ts

**Do**:
- Frame NRPG as an industry standard with practitioner authority.
- Use amber for emphasis and standards-plaque underlines only.

**Don't**:
- Never present NRPG as a regulatory body — it is an industry standard.
- Banned words: `we`, `our`, `i`, `us`, `my`.

## 8. Responsive Behavior

Aspect ratios: `1920×1080`, `1080×1920`, `1080×1080`. Headline scales 96→72→56pt. Standards plaques always render at full-width minus safe area.

## 9. Agent Prompt Guide

- **Voice**: authoritative + expert, medium cadence. Audience: industry training coordinators and response-network operators.
- **Default channel**: LinkedIn.
- **Voiceover**: `EXAVITQu4vr4xnSDxMaL`, narration, en-AU.
- **Signature motion**: `rise`. Base 22 frames @ 30fps.
- Example prompt: *"Open on neutral.50 (#FAF8F2) with a navy (#1A2A4F) standards plaque. Headline in Inter ExtraBold 88pt, underline in amber (#F2B33D). Use `signature: rise`, 22 frames."*
