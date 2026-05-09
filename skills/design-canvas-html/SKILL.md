---
name: design-canvas-html
description: Generates a self-contained `{slug}.html` preview file that demonstrates a brand's full design system (palette + WCAG contrast + typography scale + component recipes + motion samples + optional 3D scene) inline — no server, no build, opens directly in any browser. Used by design-approve to ship a portable canvas alongside the canonical spec files. Mirrors the routes in preview-canvas/app/brand/[slug] but flattened into one HTML file.
automation: automatic
intents: design-canvas-html, generate-html-preview, brand-html-preview, standalone-canvas
---

# design-canvas-html

The portable canvas. Takes a brand's spec triple and emits ONE HTML file that runs anywhere — no Next.js server, no node_modules. The user can open it directly, send it to a client, or commit it next to the spec files.

## Triggers

- `design-approve` calls after writing canonical specs.
- User says "regenerate the HTML preview for {slug}".
- User says "give me a single-file design preview I can send to {client}".

## Inputs

- `slug` — brand slug
- `outputPath` (default: `Synthex/packages/brand-config/src/brands/{slug}.html`) — where to write the file

## Method

1. **Load specs**: `loadDesign(slug)` + `tryLoadMotion(slug)` + `tryLoadScene(slug)`. If `.design.md` is missing, fail.

2. **Resolve token references** — every `{colors.primary}` style ref gets dereferenced to its hex / px value before injection.

3. **Generate HTML** with these inline sections (matches the structure of `preview-canvas/app/brand/[slug]/page.tsx`):

   - **<head>**: brand `name` + `description` + Inter / JetBrains Mono / brand-typeface CDN links if Google-Fonts-served
   - **Header**: brand display name + tagline + colour family
   - **Palette**: every colour token rendered as a swatch (hex code + name)
   - **Contrast badges**: WCAG AA / AAA badges for `(on-X, X)` pairs (computed inline via embedded `contrastRatio` JS)
   - **Typography**: every `typography.*` token rendered with sample text at correct size/weight/line-height/letter-spacing
   - **Components**: every `components.*` recipe rendered as a CSS block (cta-primary, card, mono-chip, etc.)
   - **Motion**: only if `.motion.md` exists. CSS keyframes derived from `easings.*` cubic-bezier values + `durations.*`. Show one square per easing animating left-right with the easing curve, looped reversed.
   - **Scene preview** (optional): if `.scene.md` exists, embed Three.js via CDN (`<script src="https://unpkg.com/three@0.169/build/three.module.js">`) and render the first scene preset as a `<canvas>`. Keep it lean — no R3F (R3F needs a build).
   - **Footer**: file paths of source specs + generation timestamp

4. **Inline everything** — no external CSS files, no external JS modules except Three.js from CDN (if scene present). The file should `file://` open in any browser without 404s.

5. **Write** to `outputPath`. Default puts it next to the spec files. Print the absolute path to stdout.

## Implementation

The skill executes a small Node script (lives at `Pi-Dev-Ops/preview-canvas/scripts/generate-html.mjs`) that:

1. Reads the three spec files.
2. Builds the HTML string from a template.
3. Inlines colour tokens as CSS custom properties (`:root { --color-primary: #E55A2B; ... }`).
4. Inlines typography tokens as utility classes (`.t-display-xl { font-family: ...; font-size: ...; }`).
5. Inlines motion tokens as `@keyframes` + animation rules.
6. Optionally embeds Three.js scene from `.scene.md`.
7. Writes to `outputPath`.

## Output

A single `.html` file at the requested path. Self-contained. Clickable (opens in default browser via `open <path>`).

Example: `Synthex/packages/brand-config/src/brands/ra.html` shows RA's full design system in one document.

## Boundaries

- **Never depend on Node modules at runtime.** The HTML must work offline (Three.js from CDN is the one exception, and it must degrade gracefully if offline).
- **Never include the canvas's editable / interactive controls.** This is a *read-only* preview, not the design board.
- **Never inline secrets or API keys.** The HTML is shareable; treat it as public.
- **Never write to canonical brand-config paths if the file already exists** without confirming with the user — prevent accidental overwrites of carefully-tuned previews.

## Reused

- `Pi-Dev-Ops/remotion-studio/src/brands/loadDesign.ts` / `loadMotion.ts` / `loadScene.ts` — spec loaders
- `Pi-Dev-Ops/preview-canvas/lib/loadSpecs.ts` — `contrastRatio`, `wcagLevel` helpers (the same ones the canvas Palette component uses)
- `Pi-Dev-Ops/preview-canvas/components/{Palette,Typography,ComponentGrid,MotionStrip,SceneStage}.tsx` — visual references for the HTML template (re-implemented as plain HTML/CSS/JS)

## Hands off to

`design-approve` (caller). Returns the absolute path of the generated `.html` file.
