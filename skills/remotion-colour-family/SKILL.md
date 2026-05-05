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
- `school` *(optional)*: `editorial-monocle` | `modern-minimal` | `warm-soft` | `tech-utility` | `brutalist-experimental` — visual-school preset (open-design lineage). Selects the type-character, contrast bias, and accent role *before* family heuristics run. Default: `modern-minimal`.
- Existing palette (if extending)

## Method

1. **School preset** — apply the `school` bias *first*. Each school constrains hue range, lightness range, neutrals temperature, and accent saturation:

   | School | Hue bias | Lightness bias | Neutrals | Accent saturation | Reference (vendored) |
   |---|---|---|---|---|---|
   | `editorial-monocle` | warm earth (terracotta/clay/sand) | high (parchment / ivory) | warm grays only — every gray carries yellow-brown undertone | one chromatic accent, deeply earthy | `_library/claude/`, `_library/monocle/` (if present) |
   | `modern-minimal` | cool neutral (slate/blue-gray) | balanced | true grays | one electric accent, used <3× per viewport | `_library/airbnb/`, `_library/cal/` |
   | `warm-soft` | warm pastels (peach/blush/cream) | high | warm grays + cream tints | low-saturation rose/coral | `_library/airtable/`, `_library/cafe/` |
   | `tech-utility` | indigo / cyan / slate | low (dark surfaces preferred) | cool grays toward slate-900 | cyan signal accent, used only on deltas / state | `_library/binance/`, `_library/arc/` |
   | `brutalist-experimental` | high-contrast primary on raw white | extreme high + extreme dark | pure black/white only | sharp neon, used aggressively | `_library/brutalism/`, `_library/bold/` |

2. **Family heuristics** — applied *after* school. Family supplies the canonical adjacents:
   - `safety`: navy + emergency orange + ivory
   - `restoration`: teal + slate + lime
   - `industrial`: graphite + steel + amber
   - `consumer`: hero red/blue + warm white + slate
   - `training`: terracotta + cream + ink
3. **Generate in OKLch** — work in OKLch colour space, not HSL, so hue rotations preserve perceived lightness. Convert hex anchors to OKLch first; rotate hue ±30°/±60° while clamping lightness to the school's band. Snap output back to hex for `BrandConfig` storage. Keep an `oklch` sibling field in the contrast report for downstream Tailwind-4 consumers (Phase 2).
4. **Determinism** — same `(primary, family, school)` triple MUST yield the same output palette across runs. No randomness; no temperature; no LLM interpolation. The generator is a pure function of its inputs.
5. **Build neutrals** — interpolate between `oklch(99% 0 hue)` (50) and `oklch(15% 0 hue)` (900), tilting `chroma` toward the primary's hue per the school bias (warm-soft pulls neutrals warm; tech-utility pulls them cool).
6. **Build semantics** — pick `success`/`warning`/`danger` from a fixed pool that doesn't clash with primary.
7. **Build dark variant** — invert neutrals (`50 ↔ 900` lightness) and shift primary up 8% lightness in OKLch space.
8. **Validate** — for each pair `(primary, neutral.50)`, `(primary, neutral.900)`, `(secondary, neutral.50)`, `(accent, secondary)`, ensure contrast ≥ 4.5 (WCAG-AA). If not, regenerate the failing slot. Brutalist-experimental requires ≥ 7.0 (AAA).

## Output

A complete `BrandColour` object suitable for direct insertion into `BrandConfig.colour`. Plus a contrast report including OKLch coords for Phase 2 web consumption:

```jsonc
{
  "school": "modern-minimal",
  "family": "restoration",
  "tokens": {
    "primary": { "hex": "#0E7C7B", "oklch": "oklch(48% 0.10 195)" },
    "neutral": {
      "50":  { "hex": "#F5F7F8", "oklch": "oklch(97% 0.005 200)" },
      "900": { "hex": "#0E1518", "oklch": "oklch(15% 0.010 215)" }
    }
  },
  "passes": [ { "fg":"#F5F7F8", "bg":"#0E7C7B", "ratio": 7.21, "level":"AAA" } ],
  "fails": []
}
```

## Boundaries

- Never deliver a palette with any AA failure — block and request founder input on the offending slot.
- Never override an explicit `darkVariant` set by the brand.
- Never use red as a primary unless `family === 'consumer'` and the brand name explicitly anchors red.
- Never reach for an LLM mid-generation — the function is deterministic. If determinism fails (same input → different output across runs), that's a bug in the generator, not a feature.
- Never blend two schools — pick one. Mixing `editorial-monocle` warmth with `tech-utility` slate produces the muddy "AI-default" palette every brand starts with.

## Hands off to

`remotion-brand-codify` writes the result into `src/brands/{slug}.ts`.
