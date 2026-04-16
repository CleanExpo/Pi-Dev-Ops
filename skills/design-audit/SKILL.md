---
name: design-audit
description: Design quality auditor. Detects 24 anti-patterns in UI code (impeccable patterns), critiques visual hierarchy and UX, polishes components to shipping quality. Provides /critique, /audit, /polish, and /bolder commands.
automation: manual
intents: design, review
---

# Design Audit Skill

The quality gate of the design stack. Runs after `ui-component-builder` ships a component
and before it goes to production. Identifies technical flaws, UX problems, and aesthetic
anti-patterns without touching functionality.

**Read `DESIGN.md` before auditing. Audit against the project's design system, not generic best practices.**

---

## Slash Commands

### /audit [area]
**Technical quality check — no edits, only findings.**

Reports issues across: accessibility, performance, responsive layout, token compliance, animation correctness.

Output format:
```
AUDIT FINDINGS — [component name]

🔴 Critical (must fix before ship)
  - [issue] at [file:line]

🟡 Warning (should fix)
  - [issue] at [file:line]

🟢 Passed
  - [checks that passed]

Score: X/10
```

### /critique [area]
**UX + visual design review — no edits, only observations.**

Evaluates: visual hierarchy, content clarity, emotional resonance, information density, consistency with DESIGN.md.

### /polish [area]
**Final pass before shipping.** Makes targeted improvements to:
- Spacing consistency (enforce DESIGN.md spacing scale)
- Typography precision (line-height, letter-spacing, weight)
- Hover/focus state completeness
- Micro-animation quality

### /bolder
**Amplify a design that's too timid.** Use when a design is correct but forgettable.
Increases visual contrast, strengthens typographic hierarchy, adds one deliberate moment of delight.

### /quieter
**Tone down a design that's fighting for attention.** Use when too many elements compete.
Reduces weight of secondary elements, simplifies colour usage, creates clear focal point.

### /distill
**Strip to essence.** Remove every element that doesn't answer: "does the user need this to complete their task?"

---

## The 24 Anti-Patterns (run `npx impeccable detect src/`)

These are automatically detectable flaws. A design audit must check all 24:

### Layout & Structure
1. **Side-tab borders** — coloured left-border on tab/nav items is overused. Use background fill instead.
2. **3-equal-card hero** — three equal-width cards as the primary page layout. Asymmetry is stronger.
3. **Centered hero with centered text** — everything centered feels like a template. Offset the layout.
4. **Flexbox percentage math** — `flex: 0 0 33.333%` instead of CSS Grid. Breaks at edge cases.
5. **Off-scale spacing** — `mt-7`, `px-3.5`, `gap-[13px]` — values not in the design system.

### Color & Visual
6. **Purple/neon gradient** — `from-purple-500 to-blue-600` is the default AI aesthetic. Replace.
7. **Dark glow abuse** — `shadow-lg` on dark backgrounds has zero visibility. Shadows are for light UIs.
8. **Transparent overlay mismatch** — using `bg-black/50` on a dark surface — undetectable.
9. **Status colour decoration** — using green/red for non-status elements (purely decorative).
10. **Missing tinted neutrals** — `gray-*` classes instead of `zinc-*` or brand-tinted equivalents.

### Typography
11. **Skipped heading levels** — `<h1>` to `<h3>` with no `<h2>` — accessibility and hierarchy violation.
12. **Line-length violation** — prose wider than 75ch — illegible for reading.
13. **Uniform font weight** — all text `font-normal`. No hierarchy established through weight.
14. **Missing tabular numerals** — numbers in tables/metrics without `font-variant-numeric: tabular-nums` cause column misalignment.
15. **Monospace for prose** — using a code font for descriptive text.

### Motion & Interaction
16. **Bounce easing** — `cubic-bezier(0.34,1.56,0.64,1)` for UI transitions — feels cartoonish.
17. **Animating layout properties** — animating `top`, `left`, `width`, `height` instead of `transform`.
18. **No reduced-motion handling** — animations not wrapped with `prefers-reduced-motion: reduce`.
19. **useState for spring physics** — using React state for cursor magnetic effects causes jank. Use Framer Motion `useMotionValue`.

### Interaction States & Accessibility
20. **Missing focus ring** — `:focus-visible` with no visible indicator. Keyboard users invisible.
21. **Small touch targets** — interactive elements below 44×44px on mobile.
22. **Missing icon button labels** — `<button><svg /></button>` with no `aria-label`.
23. **Missing empty state** — list/collection component with no empty state — renders blank.
24. **Missing loading state** — data-fetching component with no skeleton or spinner.

---

## Typography Audit (impeccable patterns)

### The 3-word brand test
Before selecting or validating a font choice, ask: what are 3 concrete words describing the brand personality?

- Pi-CEO: **authoritative · precise · technical**
- A font matching this: Geist (engineered, precise, modern) ✅ Not: Poppins (rounded, friendly ❌)

### Anti-reflexes (fonts that don't fit despite feeling "safe")
- "It's a tech product → use Inter" — Inter is fine but generic. Geist is more precise.
- "It's serious → use a serif" — wrong reflex. Precision can be sans-serif.
- "It's friendly → use rounded fonts" — wrong if the brand is powerful, not approachable.

### Font pair validation rules
- Heading and body fonts must have compatible x-heights
- Two fonts from the same category at the same size = mistake, not choice
- Weight jump of at least 300 between body and heading (e.g. 400 → 700)

---

## Color Audit (OKLCH)

When auditing colour choices, evaluate in OKLCH space (not HSL):
- HSL `hsl(220, 70%, 50%)` can look different at same lightness across hues
- OKLCH `oklch(55% 0.18 250)` provides perceptually uniform lightness
- Tinted neutrals must be hued toward the **brand colour specifically**, not generic warm/cool

To convert hex → OKLCH: use `oklch.com` or the CSS `color()` function.

---

## UX Writing Audit

Flag these in any copy within components:

| Bad | Better |
|-----|--------|
| "Click here" | "[specific action]" |
| "Error occurred" | "[what failed] — [how to fix]" |
| "Loading..." | "Loading [specific content]..." |
| "No data" | "No [specific content type] yet — [action to add]" |
| "Are you sure?" | "Kill session RA-1234? This cannot be undone." |
| "Success!" | "[What specifically succeeded]" |
| "Invalid input" | "[Which field] [what's wrong]" |

---

## Audit Scoring Rubric

| Dimension | 1–3 (Fail) | 4–6 (Marginal) | 7–9 (Pass) | 10 (Ship) |
|-----------|-----------|----------------|------------|-----------|
| DESIGN.md compliance | Token violations throughout | Minor deviations | All tokens correct | Exemplary — extends the system |
| State completeness | Missing 2+ states | Missing 1 state | All states present | All states + edge cases |
| Accessibility | Missing labels, focus, targets | One a11y gap | WCAG AA compliant | WCAG AAA |
| Anti-patterns | 5+ present | 2–4 present | 0–1 present | Zero, and pattern actively avoided |
| Typography | No hierarchy | Weak hierarchy | Clear hierarchy | Masterful — every level earns its role |
