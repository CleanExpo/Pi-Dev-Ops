# Brand Spec Contract — `BrandConfig` vs `design.md` vs `motion.md` vs `scene.md`

> Single source of truth for **where each token lives**. When in doubt, consult this file before adding a field.

Phase B (2026-05-07) extends the contract from 2 layers to 4. Visual tokens, motion tokens, and 3D/WebGL tokens each get their own spec-conformant file; runtime and behaviour stay in TypeScript.

| Artifact | Path | Owns | Validator |
|---|---|---|---|
| `BrandConfig.ts` | `Synthex/packages/brand-config/src/brands/{slug}.ts` | Runtime + behaviour: voice, voiceover, audience, channel, forbiddenWords, identity strings, signature enum, transitionFrames | `tsc --noEmit` |
| `{slug}.design.md` | `Synthex/packages/brand-config/src/brands/{slug}.design.md` | Visual tokens: colour, typography, spacing, components, layout, elevation | `@google/design.md lint` |
| `{slug}.motion.md` | `Synthex/packages/brand-config/src/brands/{slug}.motion.md` | Motion tokens: durations, easings, signature choreography, stagger logic, spring physics, GSAP triggers, scroll behaviour | `motion-md-validate.sh` (zod) |
| `{slug}.scene.md` | `Synthex/packages/brand-config/src/brands/{slug}.scene.md` | 3D / WebGL tokens: Three.js scene presets, lighting, materials, camera moves, shaders, performance budgets | `scene-md-validate.sh` (zod) |

All four are **first-class authored artifacts**. None is generated from the others (except the 9-section human-readable projection at `Pi-Dev-Ops/remotion-studio/src/brands/{slug}.md`, which IS derived).

## Token ownership table

| Token | `BrandConfig.ts` | `{slug}.design.md` | `{slug}.motion.md` | `{slug}.scene.md` |
|---|:---:|:---:|:---:|:---:|
| `slug` | ✅ | | | |
| `legalName`, `displayName` | ✅ | | | |
| `tagline` | ✅ | | | |
| Colour hexes (primary/secondary/accent/neutral/semantic) | | ✅ | | |
| Colour family classification (`restoration`, `safety`, etc.) | ✅ | | | |
| Dark variant colour overrides | | ✅ | | |
| Typography family / weight / src | | ✅ | | |
| Type scale (display / h1 / h2 / body / caption px) | | ✅ | | |
| Spacing scale | | ✅ | | |
| Rounded scale (border radii) | | ✅ | | |
| Component recipes (CTA, card, badge, mono-chip) | | ✅ | | |
| Layout grid + safe areas | | ✅ | | |
| Elevation / shadow tokens | | ✅ | | |
| Logo paths (`primary`, `inverted`, `icon`) | ✅ | | | |
| Logo `safeAreaPx` | ✅ | | | |
| Motion `durations.fast/base/slow` (frames) | | | ✅ | |
| Motion `easings.*` (named cubic-bezier curves) | | | ✅ | |
| Motion `signature` enum (rise/sweep/iris/pulse/whip) | ✅ | | | |
| Motion `transitionFrames` | ✅ | | | |
| Choreography `stagger`, `delay`, `repeat`, `yoyo` | | | ✅ | |
| Spring physics (damping / stiffness / mass) | | | ✅ | |
| GSAP `scrollTrigger` defaults (start/end/scrub/pin) | | | ✅ | |
| Scene presets (`hero`, `feature-block`, `closer`) | | | | ✅ |
| Lighting rigs (key/fill/rim, intensities) | | | | ✅ |
| Materials (PBR, transmission, custom shaders) | | | | ✅ |
| Camera moves (orbit, dolly, FOV, focal point) | | | | ✅ |
| Performance budgets (max draw calls, max polys, target FPS) | | | | ✅ |
| Voice `tone[]`, `forbiddenWords[]`, `requiredCadence` | ✅ | | | |
| ElevenLabs `voiceId`, `style`, `locale` | ✅ | | | |
| `audience.primary/secondary` | ✅ | | | |
| `defaultChannel` | ✅ | | | |
| `doNot[]` (brand-specific prohibitions) | ✅ | | | |
| `pillars.values[]`, `readingLevel` | ✅ | | | |

## Why split this way

1. **Visual tokens (`.design.md`)** are read by *visual generators* — Remotion compositions, image briefs, web component generators, Tailwind exports, the preview-canvas. They benefit from the open `@google/design.md` schema, the lint/diff/export CLI, and the YAML-front-matter format other tools (Figma, json-render, DTCG) can consume.

2. **Motion tokens (`.motion.md`)** were promoted out of `BrandConfig.ts` in Phase B (2026-05-07) because motion is no longer just frame counts + cubic-bezier strings — it now needs to express choreography, stagger, spring physics, GSAP scroll-triggers, and loop semantics that the preview-canvas and downstream consumers (composition-builder, image briefs) all read declaratively. The signature *enum* stays in `.ts` (it's a runtime selector that picks among `signatureEntry()` implementations); the *durations and easings* table moves to `.motion.md`.

3. **3D / WebGL tokens (`.scene.md`)** are a Phase B addition. Three.js scenes, lighting rigs, materials, and camera presets are declarative inputs to a renderer (`@react-three/fiber` in the canvas, or a future Remotion 3D scene). They're optional — most brands won't have a `.scene.md`. When present, they unlock hero panels and signature 3D moments without ad-hoc TSX.

4. **Runtime + behaviour (`BrandConfig.ts`)** is read by *non-visual code paths* — voice gates (forbidden-word linters), voiceover synthesis, channel routing, audience-targeted copy. It needs to stay in TypeScript so consumers get type errors at compile time, not runtime.

## Rules

- **Never duplicate a token.** If `colour.primary` lives in `.design.md`, do not also add it to `.ts`. The composition reader resolves both at load time.
- **Never reference across the boundary inside a single source file.** TypeScript can `import` from `loadDesign(slug)` to read visual tokens at runtime; `.design.md` cannot reference `BrandConfig` fields.
- **The 9-section `.md` projection in `remotion-studio/src/brands/{slug}.md` is regenerated, never hand-edited.** Source of truth = `.ts` + `.design.md`.
- **Colour family classification stays in `.ts`** (it's an enum that drives downstream choices like illustration style and stock-photo selection — behaviour, not a visual token).
- **`safeAreaPx` stays in `.ts`** because it's enforced by motion code (logo entry/exit choreography), not by static CSS.

## Aura integration (`aura.build`)

Aura is a Claude Agent skill registry + AI website builder. Three integration paths flow through this contract:

### 1. Vendored skills (reference layer)
A curated subset of Aura skills lives at `~/.claude/skills/aura/` for cross-reference during brand-onboarding and design-pass work. Most relevant:

| Aura skill | Source | What it does | When to use |
|---|---|---|---|
| `Stitch-UI-Full` | community | Generates DESIGN.md files for AI-driven screen generation | Initial draft of `{slug}.design.md` for a brand-new brand |
| `UI Design System` | davila7/claude-code-templates | Toolkit for tokens, responsive, accessibility, handoff | Audit an existing `.design.md` for handoff completeness |
| `Tailwind Design System v4` | wshobson/agents | Design tokens + React UI components | When exporting `.design.md` to a Tailwind config (`design.md export` does this too) |
| `Frontend Design for Distinctive Interfaces` | anthropics/skills | Distinctive, production-grade interface patterns | Pressure-test a `.design.md` for genericness before founder review |
| `Web Interface Guidelines` | vercel-labs/web-interface-guidelines | UI/accessibility/performance checklist | Pre-merge check on web consumers of `.design.md` |
| `Web Design Reviewer` | github/awesome-copilot | Inspects layouts, applies fixes, re-verifies | Visual QA pass on rendered output |

### 2. Onboarding loop (Aura → us)
For a NEW brand, the founder may drive `Stitch-UI-Full` through Aura's web builder to draft an initial `{slug}.design.md`. The output drops into `Synthex/packages/brand-config/src/brands/{slug}.design.md`, then `remotion-brand-codify` writes the matching `.ts` runtime fields and the 9-section `.md` projection. Lint via the standard hook.

### 3. Downstream consumer (us → Aura)
Once `{slug}.design.md` is shipped, it can be `@`-referenced inside Aura's website builder to generate landing-page mockups in the brand's identity. Same spec, both directions — the `@google/design.md` format is the lingua franca.

### Boundary still applies
Aura sees only `.design.md` (visual tokens). It never sees `BrandConfig.ts` (voice / voiceover / motion / forbiddenWords). Output from Aura must NOT introduce duplicate tokens that already live in `.ts` — it's a visual-only surface.

## Migration check

A clean split means:
- `grep -E "primary: '#" Synthex/packages/brand-config/src/brands/*.ts` returns **no matches** (all colour hexes moved to `.design.md`).
- `grep -E "fontSize|fontFamily" Synthex/packages/brand-config/src/brands/*.ts` returns **no matches** (typography moved to `.design.md`).
- `grep -E "signature:|durations:|easing:" Synthex/packages/brand-config/src/brands/*.design.md` returns **no matches** (motion stays in `.ts`).
- `grep -E "forbiddenWords|elevenLabsVoiceId" Synthex/packages/brand-config/src/brands/*.design.md` returns **no matches** (voice/voiceover stays in `.ts`).
