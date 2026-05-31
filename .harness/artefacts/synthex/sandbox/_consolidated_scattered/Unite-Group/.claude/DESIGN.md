# DESIGN.md — Unite-Group (Nexus)

> The brand contract every AI agent (Claude Code, Claude Design, Cursor, v0, Aura)
> reads before producing UI, copy, or motion for the Unite-Group parent /
> Nexus CRM. Source of truth at
> `Synthex/packages/brand-config/src/brands/unite.ts`. This file is the human-
> and agent-readable projection plus Phill's 7 non-negotiable rules.
>
> **This is the empire's flagship surface.** Phill's CEO Command Center, the
> portfolio dashboard, and the autonomous-agency control plane all render
> through this app.
>
> Updated: 2026-05-11. Spec: Google DESIGN.md v1 (community implementation).

---

## Brand Voice

- **Legal name:** Unite Group
- **Display name:** Unite Group
- **Tagline:** Connected service for the field.
- **Audience:** field-services operators across the Unite portfolio
- **Tone:** warm, expert, founder-led, empire-building, long-term thinking
- **Cadence:** medium.
- **Voice register:** founder-led, not startup-speak. No "disruption", no
  "unicorn", no VC-culture language. Build the kind of brand equity that
  commands a $2B exit multiple.
- **Default channel:** LinkedIn.

---

## Visual Tokens

### Colour
| Token | Hex | Use |
|---|---|---|
| `--unite-primary` | `#E55A2B` | Candy orange dark — brand primary |
| `--unite-secondary` | `#1E293B` | Slate-800 — body chrome |
| `--unite-accent` | `#FBBF24` | Amber — signal / highlight |
| `--neutral-50` | `#F8FAFC` | Canvas |
| `--neutral-100` | `#E2E8F0` | Surface |
| `--neutral-500` | `#64748B` | Muted text |
| `--neutral-900` | `#0F172A` | Body text |
| `--success` | `#16A34A` | Pass |
| `--warning` | `#D97706` | Attention |
| `--danger` | `#DC2626` | Danger |

### CEO-Surface Tokens (Phill Rule 6 — Gun Metal + Candy Red)

The Unite-Group Command Center IS the CEO register. These tokens dominate.

| Token | Hex | Use |
|---|---|---|
| `--canvas` | `#0e1014` | Gun Metal base — all CEO views |
| `--red-500` | `#b30000` | Candy Red primary — primary action |
| `--orange-400` | `#e07020` | CEO secondary |
| `--green-500` | `#00a854` | CEO success indicator |

### Typography
- **Display:** Inter, weight 700.
- **Body:** Inter, weight 400.

### Radius
- **CEO register (default for this repo): 4–6px (sharp).**
- Client-facing surfaces (when present): 10px (soft).

### Motion
- **Signature:** rise (vertical reveal — confident, building).
- Durations (frames @ 30fps): fast 10, base 20, slow 36.
- Easing: expo-out / expo-in / expo-in-out.
- Transition between scenes: 14 frames.

---

## Forbidden Patterns

### Icons (Phill Rule 1)
- **NO Lucide, HeroIcons, FontAwesome, or any other icon library in app code.**
  This rule originated here. Every Unite-Group view must use custom
  geometric marks from `src/components/ui/marks.tsx`.

### AI-Slop Phrases (brand-guardian global banned list)
- "In today's fast-paced world", "Game-changer", "Seamless" (unless quoting),
  "Leverage" (as verb), "Robust", "Cutting-edge", "State-of-the-art",
  "Dive into" / "delve into", "It's worth noting", "In conclusion" / "To
  summarise" as paragraph openers, "Our passionate team", "End-to-end
  solution", "Best-in-class", "Empower" / "empowering", "Unlock [potential]",
  rhetorical question paragraph openers.

### Unite-Group-Specific Forbidden
- Never present Unite Group as a single-vertical company — it spans multiple
  service lines.
- No startup-speak ("disruption", "unicorn", "10x", "ninja", "rockstar").
- No VC-culture language ("traction", "moat" used loosely, "category creation"
  without proof).
- No "AI agency" framing — Unite-Group is an autonomous agency holding
  company building toward a $2B exit. The framing is portfolio + autonomy,
  not "we use AI".

### Visual
- No generic AI aesthetics (purple gradients, glowing brains, blue particles).
  Phill Rule 3.
- No placeholder logos or initials for any portfolio business or client.
  Phill Rule 4. Every business in the portfolio (DR, NRPG, RA, CARSI, CCW,
  Synthex) gets its real logo.
- No Lorem ipsum.
- **No headline metrics without an action.** Phill Rule 5 — "74/100 is not a
  $2B CRM". Every number on a CEO surface is paired with WHAT TO DO.

---

## Required Patterns

### Custom Geometric Marks (Phill Rule 2 — Option B)
All visual indicators, navigation symbols, and status marks must be
purpose-designed SVGs unique to Unite-Group.

Grammar:
- 24×24 viewBox
- 1.5px stroke, `strokeLinecap="square"`, `strokeLinejoin="miter"`
- Sharp corners only — no rounded ends
- 1–3 path elements maximum per mark
- Derived from the hexagon in the Unite-Group logo mark

Marks are stored in `src/components/ui/marks.tsx`. Before adding any
icon-like element, check this file first. If missing, design one following
the grammar above.

### Real Logos (Phill Rule 4)
- Every business in the system gets its real logo, not initials or
  placeholder squares.
- Logo auto-fetch via `/api/logo-fetch?domain=`.
- Store at `public/logos/{slug}.png` or SVG.
- Use `BusinessLogo` component with geometric-mark fallback.
- Portfolio business logos: DR, NRPG, RestoreAssist, CARSI, CCW, Synthex.

### CEO-Facing Surfaces (Phill Rule 5)
This repo IS the CEO surface. Every primary view must:
- Show **TODAY'S PRIORITIES** — what needs the CEO's attention right now.
- Pair every metric with an action or recommendation.
- Health scores live in a background strip, never as the headline.
- Decisions over dashboards.

### Design Tokens (Phill Rule 6)
- No hardcoded colours. Use the CSS variables in `## Visual Tokens`.
- CEO register uses sharp radii (4–6px). Client register uses soft (10px).
- No inline typography. Use the typography tokens.

### Autonomy (Phill Rule 7)
- Anything a human does manually for a client (logo fetch, monitoring,
  reports, content production) must be automated.
- The autonomous-agency thesis depends on this — "Autonomous = Professional".

---

## Approval Gates

Before any client-facing or CEO-facing surface ships to production:

1. **brand-guardian skill** returns `APPROVED`.
2. **qa-lead skill** passes the rubric.
3. **One hallucination = automatic REVISE.**
4. **The $2B filter** — every surface here advances the exit thesis. Phill
   reviews the Command Center weekly; surfaces that don't help the CEO
   decide get cut.

---

## CI Lint Integration

This repo runs the DESIGN.md lint on every PR via
`.github/workflows/design-lint.yml`. The lint asserts:

1. `.claude/DESIGN.md` exists.
2. All 6 required H2 headings are present.
3. No **net-new** imports from `lucide-react`, `@heroicons/react`, or
   `@fortawesome/*`. Baseline at `.github/design-md-lint.baseline.txt`.
4. AI-slop phrase scan (warn-only in v1).

To run locally: `bash .github/scripts/design-md-lint.sh`.

Existing CI: `ci.yml`, `review-board.yml`. design-lint runs alongside on
every PR.

---

## References

- Source of truth (typed): `Synthex/packages/brand-config/src/brands/unite.ts`
- Visual tokens (.design.md): `Synthex/packages/brand-config/src/brands/unite.design.md`
- Nexus design system: `~/2nd Brain/2nd Brain/Wiki/nexus-design-system.md`
- Phill's 7 design rules: `~/.claude/projects/-Users-phill-mac-2nd-Brain/memory/feedback_design_preferences.md`
- Brand guardian skill: `~/.claude/skills/brand-guardian/SKILL.md`
- Pattern reference: `~/2nd Brain/2nd Brain/Wiki/design-system-approach.md`
- Exit thesis: `~/2nd Brain/2nd Brain/Wiki/exit-thesis.md`
