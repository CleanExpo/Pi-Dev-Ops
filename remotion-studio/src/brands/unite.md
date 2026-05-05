# Unite Group Design System

> Projection of `unite.ts`. Source of truth: `src/brands/unite.ts`. Do not hand-edit — regenerate via `remotion-brand-codify`.
> Tagline: *Connected service for the field.*

## 1. Visual Theme & Atmosphere

Warm + expert. The umbrella brand — multi-vertical, must feel connective rather than vertical-specific. Trust-blue primary, amber signal-accent. Inter throughout. The system reads as *holding company with field empathy*, not corporate parent. Industrial colour family but warmer than Synthex.

## 2. Color Palette & Roles

| Role | Token | Hex |
|---|---|---|
| Primary | `colour.primary` | `#1D4ED8` (trust blue) |
| Secondary | `colour.secondary` | `#1E293B` |
| Accent | `colour.accent` | `#FBBF24` (amber signal) |
| Neutral 50 | `colour.neutral.50` | `#F8FAFC` |
| Neutral 100 | `colour.neutral.100` | `#E2E8F0` |
| Neutral 500 | `colour.neutral.500` | `#64748B` |
| Neutral 900 | `colour.neutral.900` | `#0F172A` |
| Success | `colour.semantic.success` | `#16A34A` |
| Warning | `colour.semantic.warning` | `#D97706` |
| Danger | `colour.semantic.danger` | `#DC2626` |
| Family | `colour.family` | `industrial` |

## 3. Typography Rules

- **Display**: Inter Bold (700) — slightly lighter than RA/DR for warmth
- **Body**: Inter Regular (400)
- No mono — Unite Group does not surface technical content directly; portfolio brands handle that.

Display 1.10; body 1.5.

## 4. Component Stylings

- **Primary CTA**: blue on white text; 8px radius.
- **Service-line tile**: white surface with 1px neutral.100 border, 12px radius. Each tile may carry a portfolio sub-brand colour as a top-edge accent line.
- **Banner**: blue full-bleed with amber accent bar.

## 5. Layout Principles

- 12-col grid; 96px / 64px margins.
- Service-line tile grids: 2 or 3 columns. Always show ≥3 service lines together — the umbrella must read as multi-vertical.
- Logo top-left, safe area 40px.

## 6. Depth & Elevation

- Soft shadows on service-line tiles: `0 4px 16px rgba(15,23,42,0.06)`.
- Banner uses no shadow — flat against page.

## 7. Do's and Don'ts

**Do**:
- Always show ≥2 service lines when introducing the brand.
- Use amber for the "connect" / "unite" gesture — the line that ties services together.

**Don't**:
- Never present Unite Group as a single-vertical company — it spans multiple service lines.
- Banned words: `we`, `our`, `i`, `us`, `my`.

## 8. Responsive Behavior

Aspect ratios: `1920×1080` primary; `1080×1080` for square social. Display 88→64→48pt. Service-line tiles stack vertically below 800px.

## 9. Agent Prompt Guide

- **Voice**: warm + expert, medium cadence. Audience: field-services operators across the Unite portfolio.
- **Default channel**: LinkedIn.
- **Voiceover**: `EXAVITQu4vr4xnSDxMaL`, conversational, en-AU.
- **Signature motion**: `rise`. Base 20 frames @ 30fps.
- Example prompt: *"Blue (#1D4ED8) hero with Inter Bold 80pt headline in white. Three service-line tiles rise into place via `signature: rise`, 20 frames, each with an amber (#FBBF24) top-edge accent line."*
