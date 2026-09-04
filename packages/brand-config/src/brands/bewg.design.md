---
version: alpha
name: BEWG
description: Visual identity for Building Environmental Wellness Group — independent building science investigation across Australia. Paired runtime config at bewg.ts.
colors:
  primary: "#12475E"
  secondary: "#1C2B33"
  accent: "#F0A202"
  neutral-50: "#F6F8F9"
  neutral-100: "#E3EAED"
  neutral-500: "#6B7D86"
  neutral-900: "#0C1418"
  success: "#2F8F4E"
  warning: "#E0A800"
  danger: "#B23A28"
  on-primary: "#FFFFFF"
  on-secondary: "#FFFFFF"
  on-accent: "#0C1418"
  surface: "{colors.neutral-50}"
  on-surface: "{colors.neutral-900}"
  border: "{colors.neutral-100}"
  dark-primary: "#3E9CBF"
  dark-secondary: "#131E24"
  dark-surface: "#0C1418"
  dark-on-surface: "#F6F8F9"
typography:
  display-xl:
    fontFamily: Inter
    fontSize: 88px
    fontWeight: 800
    lineHeight: 1.04
    letterSpacing: -0.03em
  display-lg:
    fontFamily: Inter
    fontSize: 60px
    fontWeight: 800
    lineHeight: 1.06
    letterSpacing: -0.025em
  display-md:
    fontFamily: Inter
    fontSize: 42px
    fontWeight: 700
    lineHeight: 1.12
    letterSpacing: -0.02em
  headline:
    fontFamily: Inter
    fontSize: 28px
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Inter
    fontSize: 19px
    fontWeight: 400
    lineHeight: 1.6
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.6
  caption:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: 500
    lineHeight: 1.4
  mono-md:
    fontFamily: JetBrains Mono
    fontSize: 14px
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: 0.01em
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  2xl: 48px
  3xl: 64px
  outer-margin-landscape: 96px
  outer-margin-portrait: 64px
  safe-area: 5%
rounded:
  sm: 4px
  DEFAULT: 8px
  md: 12px
  lg: 16px
  full: 9999px
components:
  cta-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.neutral-900}"
    rounded: "{rounded.DEFAULT}"
    padding: "{spacing.md}"
    typography: "{typography.body-lg}"
  cta-secondary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.neutral-50}"
    rounded: "{rounded.DEFAULT}"
    padding: "{spacing.md}"
  card:
    backgroundColor: "{colors.neutral-50}"
    rounded: "{rounded.md}"
    padding: "{spacing.lg}"
  input:
    backgroundColor: "{colors.neutral-50}"
    textColor: "{colors.neutral-900}"
    rounded: "{rounded.sm}"
  mono-chip:
    backgroundColor: "{colors.neutral-100}"
    textColor: "{colors.primary}"
    typography: "{typography.mono-md}"
    rounded: "{rounded.sm}"
    padding: "{spacing.sm}"
---

## Overview

Instrument-grade. BEWG is hired when somebody else has already guessed wrong, so the identity reads
like a calibrated readout rather than a services brochure: measured values in the open, the
conclusion shown with the evidence that produced it, no reassurance that the data does not support.

The palette is borrowed from the discipline's own instrument — thermal imagery, where cold wet
fabric reads deep blue and the anomaly reads amber. Blue is the whole building. Amber is the thing
that is wrong. That rule is the identity, and it is why amber never appears as decoration.

Audience: building owners and strata committees who have been told three different things by three
trades; and the insurers, assessors and lawyers who need a position that survives the other side
reading it.

## Colors

- **Primary (#12475E):** Diagnostic blue. Structural surfaces, hero grounds, the default voice of
  the brand. Deep enough to carry white display type at any size.
- **Secondary (#1C2B33):** Graphite. Body type, borders, dense technical surfaces.
- **Accent (#F0A202):** Thermal amber. Reserved for the finding — a call-to-action, an anomaly
  marker, a flagged reading. **Never** used as a background wash or a decorative rule.
- **Neutral 50 / 100 / 500 / 900:** Cool greys carrying a trace of blue, so a neutral surface next
  to primary reads as the same family rather than as unrelated grey.
- **Semantic** — success / warning / danger for system states only. Danger red is never a brand
  colour, and never marks a building finding: a severe finding is amber, because severity here is
  a measurement, not an alarm.

Dark variant lifts primary to #3E9CBF for legibility on dark surfaces; neutrals invert (50 ↔ 900).

## Typography

**Inter** carries the entire narrative. **JetBrains Mono** carries every measured value.

That split is load-bearing rather than stylistic. This trade's whole argument is the difference
between an opinion and a reading, so a moisture content, a relative humidity, a dew point, a
sample ID or a timestamp is always set in mono, and a claim never is. A reader can tell at a
glance which parts of a page are measured and which are argued.

- **Display (xl/lg/md):** Inter ExtraBold/Bold, tight leading (≤1.12), negative tracking.
- **Body (lg/md):** Inter Regular at 1.6 leading — these are long technical explanations and they
  have to stay readable at length.
- **Caption:** Inter Medium 13px for figure captions and metadata.
- **Mono:** JetBrains Mono Medium — readings, identifiers, standards codes, timestamps. Never prose.

No italic for emphasis; use weight and colour.

## Layout

Long-form technical content on a 12-column grid with a hard measure limit: body copy never exceeds
about 68 characters, because these pages are read rather than scanned. Service pages run a two-column
layout at ≥900px — narrative left, a persistent contact and routing panel right — collapsing to a
single column below that with the panel moved beneath the narrative, never hidden.

Maximum three colours per surface. Amber appears at most twice per screen.

## Elevation & Depth

Flat surfaces, 1px borders and tonal shifts express hierarchy. Shadow is used only where an element
genuinely floats above the page:

```
0 4px 14px rgba(12, 20, 24, 0.08)
```

Focus rings use primary at 40% opacity, offset outside the element bounds, and are never removed.

## Shapes

`sm` (4px) chips and inputs, `DEFAULT` (8px) buttons, `md` (12px) cards, `lg` (16px) hero and
result panels. Full rounding reserved for status pills.

## Components

- **cta-primary** — Amber fill, near-black text. At most one per screen; it is the finding.
- **cta-secondary** — Primary fill, neutral-50 text. Everything else.
- **card** — Neutral-50 surface, 1px neutral-100 border, 12px radius.
- **input** — Neutral-50 fill, 4px radius, primary focus ring. Labels always visible, never
  placeholder-only, because these forms are filled in by stressed people on phones.
- **mono-chip** — JetBrains Mono on neutral-100. Standards codes, readings, identifiers.

## Do's and Don'ts

**Do:**
- Show the measurement next to the claim it supports.
- Reserve amber for the finding and the single primary action.
- Set every reading, code and identifier in mono.
- Hold WCAG-AA on every text-on-surface pair, including amber-on-blue, which must not be used for
  body text at any size.

**Don't:**
- Never state a credential, accreditation or capability that has not been confirmed by BEWG.
- Never imply a health or medical conclusion — findings are building conditions and exposure
  indicators, never a diagnosis.
- Never use danger red to mark a building finding.
- Never use amber as a background wash or decorative rule.
- Never claim independence from remediation unless BEWG genuinely does not perform it.
