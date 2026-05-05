# Disaster Recovery Design System

> Projection of `dr.ts`. Source of truth: `src/brands/dr.ts`. Do not hand-edit — regenerate via `remotion-brand-codify`.
> Tagline: *When the worst happens, ready answers.*

## 1. Visual Theme & Atmosphere

Authoritative + reassuring. Deep navy anchors the palette to convey safety and institutional weight; warm orange accent signals action and urgency without alarm. Typography is pure Inter — operational, not decorative. Cadence is medium; voice never trivialises loss. The system reads like emergency-services literature: serious, present, available.

## 2. Color Palette & Roles

| Role | Token | Hex |
|---|---|---|
| Primary | `colour.primary` | `#0B2545` (deep navy) |
| Secondary | `colour.secondary` | `#13315C` (navy-mid) |
| Accent | `colour.accent` | `#FF8A00` (emergency orange) |
| Neutral 50 | `colour.neutral.50` | `#F4F6F8` |
| Neutral 100 | `colour.neutral.100` | `#E2E7EC` |
| Neutral 500 | `colour.neutral.500` | `#6F7B82` |
| Neutral 900 | `colour.neutral.900` | `#0B1726` |
| Success | `colour.semantic.success` | `#3FA34D` |
| Warning | `colour.semantic.warning` | `#E0A800` |
| Danger | `colour.semantic.danger` | `#C0392B` |
| Family | `colour.family` | `safety` |

## 3. Typography Rules

- **Display**: Inter ExtraBold (800)
- **Body**: Inter Regular (400)
- No mono — DR does not surface technical identifiers.

Headlines tight (1.05–1.15); body relaxed (1.4); never serif.

## 4. Component Stylings

- **Primary CTA**: orange (`#FF8A00`) on navy text; 8px radius.
- **Cards**: white surface, 1px solid neutral.100 border, 12px radius.
- **Banners**: full-width navy with orange CTA chip.
- **Status chips**: semantic colours, never the brand orange.

## 5. Layout Principles

- 12-col grid, 96px outer margin / 64px portrait.
- Headlines hold the top third; CTAs always in the lower-right safe area.
- Logo top-left, never overlapping imagery.

## 6. Depth & Elevation

- Flat surfaces with 1px navy borders.
- Elevation only for live alerts: `0 6px 20px rgba(11,37,69,0.18)`.
- Never use shadows decoratively.

## 7. Do's and Don'ts

**Do**:
- Lead with reassurance, then the action — voice is *authoritative + reassuring*.
- Use orange exclusively for CTA and emergency call-outs.
- Frame loss as recoverable; show the path forward.

**Don't**:
- Never trivialise loss in voiceover or on-screen text.
- Never use red as a primary brand colour.
- Banned words: `we`, `our`, `i`, `us`, `my`.

## 8. Responsive Behavior

Aspect ratios: `1920×1080`, `1080×1920`, `1080×1080`. Headline 96→72→56pt across landscape→square→portrait. CTA always above the safe-area fold.

## 9. Agent Prompt Guide

- **Voice**: authoritative + reassuring, medium cadence. Audience: business owners and facility managers post-incident.
- **Default channel**: LinkedIn.
- **Voiceover**: `EXAVITQu4vr4xnSDxMaL`, narration, en-AU.
- **Signature motion**: `rise` (vertical settle — composure). Base 22 frames @ 30fps.
- Example prompt: *"Open on a navy (#0B2545) full-bleed scene with Inter ExtraBold 96pt headline in neutral.50. Lift the CTA chip in orange (#FF8A00) using `signature: rise` over 22 frames."*
