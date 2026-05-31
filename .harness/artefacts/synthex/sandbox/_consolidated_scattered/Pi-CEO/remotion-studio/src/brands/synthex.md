# Synthex Design System

> Projection of `synthex.ts`. Source of truth: `src/brands/synthex.ts`. Do not hand-edit — regenerate via `remotion-brand-codify`.
> Tagline: *Synthetic intelligence at production scale.*

## 1. Visual Theme & Atmosphere

Expert + authoritative. Indigo primary with cyan signal-accent on slate-900 surfaces reads as developer-tooling for ML platform teams — precise, clean, technical without resorting to "AI-cliché" imagery. Inter ExtraBold + JetBrains Mono make it the most code-forward of the umbrella. Industrial colour family. Motion is `sweep` — decisive, lateral, no bounce.

## 2. Color Palette & Roles

| Role | Token | Hex |
|---|---|---|
| Primary | `colour.primary` | `#6366F1` (indigo) |
| Secondary | `colour.secondary` | `#0F172A` (slate-900) |
| Accent | `colour.accent` | `#22D3EE` (cyan signal) |
| Neutral 50 | `colour.neutral.50` | `#F8FAFC` |
| Neutral 100 | `colour.neutral.100` | `#E2E8F0` |
| Neutral 500 | `colour.neutral.500` | `#64748B` |
| Neutral 900 | `colour.neutral.900` | `#0F172A` |
| Success | `colour.semantic.success` | `#10B981` |
| Warning | `colour.semantic.warning` | `#F59E0B` |
| Danger | `colour.semantic.danger` | `#EF4444` |
| Family | `colour.family` | `industrial` |

## 3. Typography Rules

- **Display**: Inter ExtraBold (800)
- **Body**: Inter Regular (400)
- **Mono**: JetBrains Mono Medium (500) — every code reference, model id, and metric

Display 1.10; body 1.5; mono 1.4. Tabular nums on for any metrics.

## 4. Component Stylings

- **Primary CTA**: indigo on white text; 8px radius.
- **Code block**: slate-900 surface, neutral.50 mono text, cyan caret accent for highlights.
- **Metric tile**: white surface, mono value in display size, label in body.
- **Status chip**: semantic colour at 12% opacity background, full opacity text.

## 5. Layout Principles

- 12-col grid; 96px outer margin landscape.
- Code blocks always max-width 960px (avoid line-wrapping at scale).
- Metric tiles in 3 or 4 column grids; align to baseline.

## 6. Depth & Elevation

- Flat surfaces. Shadows only for floating overlays (modals, popovers).
- Code-block elevation: subtle inner shadow `inset 0 1px 0 rgba(255,255,255,0.04)` for depth on slate.

## 7. Do's and Don'ts

**Do**:
- Show the code, the metric, the architecture diagram — the brand earns trust through artefacts, not adjectives.
- Use cyan only for signal moments (deltas, deployment success, attention pulls).

**Don't**:
- Never imply Synthex generates training data without consent.
- Never use stock AI-cliché imagery (glowing brains, blue particles).
- Banned words: `we`, `our`, `i`, `us`, `my`, `leverage`, `synergy`.

## 8. Responsive Behavior

Aspect ratios: `1920×1080` primary; `1080×1920` for social cuts. Mono code never wraps mid-token — clamp width or shrink scale. Display 96→72→56pt.

## 9. Agent Prompt Guide

- **Voice**: expert + authoritative, medium cadence. Audience: ML engineers and platform teams shipping AI products; secondary CTOs evaluating synthetic-data infrastructure.
- **Default channel**: LinkedIn.
- **Voiceover**: `EXAVITQu4vr4xnSDxMaL`, narration, en-AU.
- **Signature motion**: `sweep`. Base 16 frames @ 30fps.
- Example prompt: *"Slate-900 (#0F172A) hero. Inter ExtraBold 96pt headline in neutral.50. Code block in JetBrains Mono with cyan (#22D3EE) caret highlight on the differentiating line. Reveal via `signature: sweep`, 16 frames."*
