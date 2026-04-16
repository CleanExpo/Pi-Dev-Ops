---
name: ui-ux-pro-max
description: Full-stack design workflow skill. Orchestrates all four design layers (intelligence, build, audit, visual-qa) end-to-end with maximum quality settings. Use for ambitious UI work — new pages, design system extensions, and design sprints.
automation: manual
intents: design, feature, review
---

# UI-UX Pro Max Skill

The full design production workflow from blank canvas to shipped, regression-tested component.
Orchestrates all four layers of the Pi-CEO design stack at maximum quality settings.

Use the individual specialist skills for targeted tasks. Use this skill when shipping something that matters.

---

## The Pro Max Workflow

### Phase 1 — Context (5 min)
```
Skill: design-intelligence
```
1. Read `DESIGN.md` — confirm tokens, font stack, motion rules
2. If the feature matches a reference brand, run:
   ```bash
   npx getdesign@latest add <brand>  # e.g. linear.app, vercel, stripe
   ```
3. If building from a reference site:
   ```bash
   npx skillui --url https://reference.example.com --mode ultra
   ```
4. Define the 3-dial settings before writing a line of code:
   - `DESIGN_VARIANCE` (layout complexity 1–10)
   - `MOTION_INTENSITY` (animation richness 1–10)
   - `VISUAL_DENSITY` (information density 1–10)

**Pi-CEO defaults:** Dashboard `3/4/7` · Landing page `6/6/3` · Settings `2/2/5`

---

### Phase 2 — Component Brief

Write a brief before coding. Template:
```
Component: [name]
Context: [where it lives in the product]
Dials: DESIGN_VARIANCE=[x] MOTION_INTENSITY=[y] VISUAL_DENSITY=[z]
States required: default, hover, active, loading, empty, error[, disabled]
Data shape: [interface / mock data description]
Reference: [brand archetype or URL if relevant]
DESIGN.md tokens: [list the specific tokens this component uses]
```

---

### Phase 3 — Build (Skill: ui-component-builder)

Generate 3 variants, then select one. The builder must produce:
- All required states (no partial implementations)
- Skeleton loader for async surfaces
- TypeScript props interface with named export
- No hardcoded hex values — Tailwind tokens or CSS variables only
- `prefers-reduced-motion` wrapper on all animations
- Keyboard navigable with visible focus ring

**21st.dev Magic workflow:**
```bash
# Search for nearest existing pattern first
21st_magic_component_inspiration("[component description]")
# Then generate variants
21st_magic_component_builder("[brief]", variants=3)
```

---

### Phase 4 — Audit (Skill: design-audit)

Run the full audit before marking anything done:

```
/audit [component-name]
```

Expect a report against all 24 anti-patterns. Must score 7/10 or above to proceed.
Fix all 🔴 Critical findings. Fix all 🟡 Warning findings where possible.

Then run the automated detector:
```bash
npx impeccable detect src/components/[ComponentName].tsx
```

Zero findings is the target. 1–2 marginal findings = acceptable with documented rationale.

---

### Phase 5 — Visual QA (Skill: visual-qa)

#### Screenshot matrix (run before every PR):
```bash
for config in "375,812,mobile" "768,1024,tablet" "1280,800,desktop" "1920,1080,wide"; do
  w=${config%%,*}; rest=${config#*,}; h=${rest%%,*}; label=${rest#*,}
  npx playwright screenshot http://localhost:3000 "qa-${label}.png" \
    --full-page --viewport-size "$w, $h" --wait-for-timeout 1500
done
npx playwright screenshot http://localhost:3000 qa-dark.png \
  --full-page --viewport-size "1280, 800" --color-scheme dark
```

#### Visual regression (for components with existing baselines):
```bash
npx playwright test tests/visual/ --project chromium-desktop
```

#### Design vs implementation diff:
Feed the Figma export / reference screenshot + the component screenshot to a vision model:
```
Compare these screenshots. List differences in:
1. Spacing and alignment
2. Typography (size, weight, colour)
3. Colour (compare against DESIGN.md tokens)
4. Missing states
5. Proportion differences
```

---

### Phase 6 — Ship Checklist

Before opening a PR, confirm all of these:

- [ ] `DESIGN.md` tokens used throughout — no hardcoded hex
- [ ] All 8 states implemented: default, hover, active, loading, empty, error, disabled, focus
- [ ] Skeleton loader built for every async data surface
- [ ] `transform` + `opacity` only animated — never `top/left/width/height`
- [ ] `prefers-reduced-motion` applied
- [ ] `aria-label` on all icon buttons
- [ ] No placeholder content (John Doe, Acme, 99.99%)
- [ ] Keyboard navigable — tab order correct, focus ring visible
- [ ] Responsive at 375px and 1280px confirmed via screenshot
- [ ] `npx impeccable detect` — zero or documented findings
- [ ] Visual regression baselines updated if intentional design change

---

## Quality Bars

| Dimension | Minimum to ship | Pro Max target |
|-----------|-----------------|----------------|
| design-audit score | 7/10 | 9/10 |
| Anti-patterns | ≤ 1 | 0 |
| States covered | 6/8 | 8/8 |
| WCAG compliance | AA | AA (AAA on typography) |
| Responsive coverage | 375 + 1280 | 375 + 768 + 1280 + 1920 |
| Visual regression | Baseline exists | Baseline + dark mode baseline |

---

## Brand Archetype Quick Reference

When the CEO asks for a specific aesthetic:

| Ask | Archetype to reference | Key tokens |
|-----|----------------------|-----------|
| "Like Linear" | linear.app | `#08090a` canvas, `#5e6ad2` accent, Berkeley Mono |
| "Like Vercel" | vercel.com | `#000` canvas, Geist, zero decoration |
| "Like Raycast" | raycast.com | Dark chrome, vibrant gradient accents |
| "Like Stripe" | stripe.com | Purple gradient, weight-300 elegance, white |
| "Like Superhuman" | superhuman.com | Purple glow, keyboard-first |
| "Pi-CEO default" | DESIGN.md | Amber + zinc, Geist, terminal authority |

```bash
npx getdesign@latest add linear.app  # Downloads Linear's full DESIGN.md
```

---

## When NOT to Use This Skill

- Simple copy change or icon swap → no skill needed
- One-off script or non-UI code → no skill needed
- Only reading existing code → `design-audit /critique` only

---

## Output Artifacts

A completed Pro Max workflow produces:
1. React component file (`dashboard/components/[Name].tsx`)
2. Updated or confirmed `DESIGN.md` (if new tokens were added)
3. 6 screenshots (4 breakpoints + dark + reference comparison)
4. `/audit` report saved to PR description or `.harness/design-audits/[name].md`
5. Visual regression baseline images (Linux CI only)
