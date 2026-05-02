---
name: remotion-colour-family
description: Generates a complete, accessible palette (primary, secondary, accent, 4-step neutral, semantic, and dark variant) from one to three hex anchors plus a colour-family classification. Validates WCAG-AA contrast for all text-on-background pairs. Triggered when a BrandConfig has fewer than 5 defined colours or contrast fails.
automation: automatic
intents: palette, contrast-check, colour-system
---

# remotion-colour-family

Builds a complete palette from minimal anchors. Reuses [`remotion-studio/src/colour/index.ts`](../../remotion-studio/src/colour/index.ts) `contrast()` helper.

## Triggers

- BrandConfig is missing `secondary`, `accent`, `neutral`, or `semantic` blocks.
- A render fails contrast: any text-on-background pair has ratio < 4.5.
- User says "extend the palette for {brand}" or "audit colour".

## Inputs

- 1-3 hex anchors (primary required; secondary, accent optional)
- `family`: `restoration` | `safety` | `industrial` | `consumer` | `training`
- Existing palette (if extending)

## Method

1. **Family heuristics** — each family has reference adjacents:
   - `safety`: navy + emergency orange + ivory
   - `restoration`: teal + slate + lime
   - `industrial`: graphite + steel + amber
   - `consumer`: hero red/blue + warm white + slate
   - `training`: terracotta + cream + ink
2. **Generate missing slots** by hue rotation (±30°/±60°) and value adjustment, then snap to nearest WCAG-AA-passing variant.
3. **Build neutrals** — interpolate between `#FFFFFF` (50) and `#000000` (900) tilted slightly toward the primary's hue.
4. **Build semantics** — pick `success`/`warning`/`danger` from a fixed pool that doesn't clash with primary.
5. **Build dark variant** — invert neutrals and shift primary up 8% lightness.
6. **Validate** — for each pair `(primary, neutral.50)`, `(primary, neutral.900)`, `(secondary, neutral.50)`, `(accent, secondary)`, ensure contrast ≥ 4.5. If not, regenerate the failing slot.

## Output

A complete `BrandColour` object suitable for direct insertion into `BrandConfig.colour`. Plus a contrast report:

```jsonc
{
  "passes": [ { "fg":"#F5F7F8", "bg":"#0E7C7B", "ratio": 7.21, "level":"AAA" } ],
  "fails": []
}
```

## Boundaries

- Never deliver a palette with any AA failure — block and request founder input on the offending slot.
- Never override an explicit `darkVariant` set by the brand.
- Never use red as a primary unless `family === 'consumer'` and the brand name explicitly anchors red.

## Hands off to

`remotion-brand-codify` writes the result into `src/brands/{slug}.ts`.
