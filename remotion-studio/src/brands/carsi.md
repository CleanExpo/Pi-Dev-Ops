# CARSI Design System

> Projection of `carsi.ts`. Source of truth: `src/brands/carsi.ts`. Do not hand-edit — regenerate via `remotion-brand-codify`.
> Tagline: *Inspection-led training.*

## 1. Visual Theme & Atmosphere

Expert + warm — the only training brand in the umbrella. Terracotta primary against a cream neutral evokes craft instruction, not a sterile classroom. Lora serif for display gives every lesson title the weight of a textbook chapter; Inter for body keeps lessons scannable. The system reads as *masterclass*, not *MOOC*.

## 2. Color Palette & Roles

| Role | Token | Hex |
|---|---|---|
| Primary | `colour.primary` | `#B85C38` (terracotta) |
| Secondary | `colour.secondary` | `#2D2A26` (warm dark) |
| Accent | `colour.accent` | `#F2E8D5` (cream highlight) |
| Neutral 50 | `colour.neutral.50` | `#FBF8F2` |
| Neutral 100 | `colour.neutral.100` | `#EFE7D9` |
| Neutral 500 | `colour.neutral.500` | `#736B5E` |
| Neutral 900 | `colour.neutral.900` | `#1A1714` |
| Success | `colour.semantic.success` | `#3FA34D` |
| Warning | `colour.semantic.warning` | `#E0A800` |
| Danger | `colour.semantic.danger` | `#C0392B` |
| Family | `colour.family` | `training` |

Every neutral is warm-toned; no cool grays.

## 3. Typography Rules

- **Display**: Lora Bold (700) — serif, for lesson and module titles
- **Body**: Inter Regular (400)
- No mono.

Display line-height 1.20 (serif breathing room). Body 1.6 (relaxed for reading). Never mix serif into body, never mix sans into display.

## 4. Component Stylings

- **Lesson card**: cream neutral.50 surface, 1px solid neutral.100, 16px radius (generous, course-material feel).
- **Primary CTA**: terracotta on cream text; 8px radius.
- **Definition tooltip**: warm-dark secondary background, cream text, 6px radius.

## 5. Layout Principles

- 12-col, 96px / 64px margins; generous section spacing (96px+).
- Module titles get full-width treatment; lesson body stays max-width 720px for readability.
- Logo bottom-right when paired with hero imagery; otherwise top-left.

## 6. Depth & Elevation

- Whisper shadows: `0 4px 24px rgba(45,42,38,0.05)` for elevated lesson cards.
- Avoid hard borders on lesson cards — use shadow + cream background to lift.

## 7. Do's and Don'ts

**Do**:
- Define clinical jargon on-screen the first time it appears.
- Lead with the lesson's payoff, then the steps.

**Don't**:
- Never use clinical jargon without on-screen definition.
- Banned words: `we`, `our`, `i`, `us`, `my`.

## 8. Responsive Behavior

Aspect ratios: `1920×1080`, `1080×1920`, `1080×1080`. Display Lora 88→64→48pt. Lesson body never exceeds 720px line length, even on landscape.

## 9. Agent Prompt Guide

- **Voice**: expert + warm, medium cadence. Audience: restoration trainees and technical inspectors.
- **Default channel**: YouTube.
- **Voiceover**: `EXAVITQu4vr4xnSDxMaL`, narration, en-AU.
- **Signature motion**: `iris` (focus-pull from edges to centre — instructional). Base 24 frames @ 30fps.
- Example prompt: *"Open on neutral.50 (#FBF8F2). Lesson title in Lora Bold 64pt terracotta (#B85C38). Definition tooltip slides in via `signature: iris`, 24 frames. Body in Inter Regular 28pt warm-dark (#2D2A26), 1.6 line-height, max-width 720px."*
