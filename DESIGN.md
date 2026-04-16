# Pi-CEO — Design System

> Read this file before building any UI component for Pi-CEO, Pi-Dev-Ops, or any Unite-Group Nexus project. This is the single source of truth for visual identity.

---

## 1. Visual Theme & Atmosphere

**Character:** Autonomous command centre. A Second Brain that executes engineering work without being asked. The visual language should feel like the control room of something powerful — not a startup dashboard, not a generic SaaS. Somewhere between a trading terminal, Linear, and Mission Control.

**Design philosophy:**
- Dark-first. The system runs 24/7. Light mode is never the default.
- Density over decoration. Every pixel earns its place.
- Motion signals state, never personality.
- Typography carries authority. Components do not need to shout.
- Zinc neutrals + amber accent. Never purple, never neon blue.

**Atmosphere keywords:** void-black precision · terminal authority · amber intelligence · Geist clarity · zero-touch confidence

---

## 2. Color Palette & Roles

### Surfaces
| Token | Hex | Role |
|-------|-----|------|
| `canvas` | `#09090b` | Page background — true near-black |
| `surface-0` | `#0f0f11` | Sidebar, primary panels |
| `surface-1` | `#18181b` | Cards, modals, elevated panels |
| `surface-2` | `#27272a` | Hover states, selected rows, code blocks |
| `surface-3` | `#3f3f46` | Active states, strong separators |

### Borders
| Token | Value | Role |
|-------|-------|------|
| `border-subtle` | `rgba(255,255,255,0.06)` | Default card/panel border |
| `border-default` | `rgba(255,255,255,0.10)` | Input borders, dividers |
| `border-strong` | `rgba(255,255,255,0.18)` | Focus rings, active states |

### Brand & Accent
| Token | Hex | Role |
|-------|-----|------|
| `brand` | `#f59e0b` | Primary CTA, links, key metrics, badges |
| `brand-dim` | `rgba(245,158,11,0.15)` | Amber tint backgrounds |
| `brand-hover` | `#fbbf24` | Button hover, link hover |

### Text
| Token | Value | Role |
|-------|-------|------|
| `text-primary` | `#fafafa` | Headings, primary content |
| `text-secondary` | `#a1a1aa` | Labels, meta, secondary content |
| `text-tertiary` | `#71717a` | Placeholder, disabled, timestamps |
| `text-disabled` | `#52525b` | Truly disabled elements |
| `text-inverse` | `#09090b` | Text on amber backgrounds |

### Status
| Token | Hex | Role |
|-------|-----|------|
| `status-success` | `#22c55e` | Complete, passed, healthy |
| `status-warning` | `#f59e0b` | Warning, in-review (shares brand amber) |
| `status-error` | `#ef4444` | Failed, critical, error |
| `status-info` | `#3b82f6` | Running, in-progress |
| `status-neutral` | `#71717a` | Killed, cancelled, unknown |

### Success tints (for status badges)
```css
.badge-success { background: rgba(34,197,94,0.12); color: #22c55e; }
.badge-error   { background: rgba(239,68,68,0.12); color: #ef4444; }
.badge-warning { background: rgba(245,158,11,0.12); color: #f59e0b; }
.badge-info    { background: rgba(59,130,246,0.12); color: #3b82f6; }
```

---

## 3. Typography Rules

**Primary font:** `Geist` (already bundled in Next.js as `next/font/local`)
**Monospace font:** `Geist Mono` (code, IDs, metrics, terminal output)
**Fallback stack:** `system-ui, -apple-system, sans-serif`

### Type Scale
| Role | Size | Weight | Line Height | Letter Spacing | Font |
|------|------|--------|-------------|----------------|------|
| Display XL | 3rem (48px) | 700 | 1.1 | -0.04em | Geist |
| Display | 2.25rem (36px) | 700 | 1.15 | -0.03em | Geist |
| H1 | 1.875rem (30px) | 600 | 1.2 | -0.02em | Geist |
| H2 | 1.5rem (24px) | 600 | 1.25 | -0.015em | Geist |
| H3 | 1.25rem (20px) | 500 | 1.3 | -0.01em | Geist |
| H4 | 1.125rem (18px) | 500 | 1.4 | 0 | Geist |
| Body LG | 1rem (16px) | 400 | 1.6 | 0 | Geist |
| Body | 0.875rem (14px) | 400 | 1.5 | 0 | Geist |
| Body SM | 0.8125rem (13px) | 400 | 1.5 | 0.01em | Geist |
| Caption | 0.75rem (12px) | 400 | 1.4 | 0.02em | Geist |
| Label | 0.6875rem (11px) | 500 | 1.4 | 0.06em | Geist |
| Mono LG | 0.9375rem (15px) | 400 | 1.6 | 0 | Geist Mono |
| Mono | 0.8125rem (13px) | 400 | 1.5 | 0 | Geist Mono |
| Mono SM | 0.6875rem (11px) | 400 | 1.4 | 0 | Geist Mono |

**Rules:**
- Use `font-variant-numeric: tabular-nums` on all numeric data (scores, tokens, costs, durations).
- Labels above inputs: uppercase, 11px, weight 500, letter-spacing 0.06em, `text-tertiary`.
- Session IDs, ticket numbers (RA-xxx), git SHAs: always Geist Mono.
- Never use a weight below 400 in UI. Never use weight 900.

---

## 4. Component Stylings

### Buttons

**Primary (amber CTA)**
```css
background: #f59e0b;
color: #09090b;
font-weight: 500;
font-size: 14px;
height: 36px;
padding: 0 16px;
border-radius: 6px;
border: none;
transition: background 150ms ease;
/* hover */ background: #fbbf24;
/* active */ transform: scale(0.98);
/* disabled */ opacity: 0.4; cursor: not-allowed;
```

**Secondary (ghost)**
```css
background: transparent;
color: #fafafa;
border: 1px solid rgba(255,255,255,0.10);
height: 36px;
padding: 0 16px;
border-radius: 6px;
/* hover */ background: rgba(255,255,255,0.05); border-color: rgba(255,255,255,0.18);
/* active */ transform: scale(0.98);
```

**Destructive**
```css
background: rgba(239,68,68,0.12);
color: #ef4444;
border: 1px solid rgba(239,68,68,0.25);
/* hover */ background: rgba(239,68,68,0.20);
```

**Icon button**
```css
width: 36px; height: 36px;
border-radius: 6px;
background: transparent;
color: #71717a;
/* hover */ background: rgba(255,255,255,0.06); color: #fafafa;
```

### Cards / Panels
```css
background: #18181b;
border: 1px solid rgba(255,255,255,0.06);
border-radius: 8px;
padding: 20px;
/* elevated (modal, popover) */
box-shadow: 0 8px 24px rgba(0,0,0,0.4), 0 1px 0 rgba(255,255,255,0.04) inset;
```

### Inputs & Text Fields
```css
background: #09090b;
border: 1px solid rgba(255,255,255,0.10);
border-radius: 6px;
height: 36px;
padding: 0 12px;
color: #fafafa;
font-size: 14px;
/* focus */
border-color: rgba(255,255,255,0.25);
outline: 2px solid rgba(245,158,11,0.25);
outline-offset: 0;
/* error */
border-color: rgba(239,68,68,0.50);
```

### Status Badges (build session states)
```css
/* Base */
height: 20px; padding: 0 8px;
border-radius: 4px;
font-size: 11px; font-weight: 500;
letter-spacing: 0.06em;
text-transform: uppercase;
white-space: nowrap;
```

### Navigation / Sidebar
```css
width: 220px;
background: #0f0f11;
border-right: 1px solid rgba(255,255,255,0.06);
/* Nav item */
height: 32px;
padding: 0 12px;
border-radius: 5px;
font-size: 13px;
color: #71717a;
/* active */ background: rgba(255,255,255,0.06); color: #fafafa;
/* hover */ background: rgba(255,255,255,0.04); color: #a1a1aa;
```

### Code / Terminal Blocks
```css
background: #0f0f11;
border: 1px solid rgba(255,255,255,0.06);
border-radius: 6px;
padding: 16px;
font-family: 'Geist Mono', monospace;
font-size: 13px;
line-height: 1.6;
color: #a1a1aa;
/* keyword */ color: #f59e0b;
/* string */ color: #22c55e;
/* comment */ color: #52525b;
```

---

## 5. Layout Principles

**Base unit:** 4px

**Spacing scale:**
| Token | Value | Use |
|-------|-------|-----|
| `space-1` | 4px | Icon gap, tight inline |
| `space-2` | 8px | Compact padding |
| `space-3` | 12px | Input padding, small gaps |
| `space-4` | 16px | Card padding (compact) |
| `space-5` | 20px | Card padding (default) |
| `space-6` | 24px | Section gap |
| `space-8` | 32px | Page section separator |
| `space-12` | 48px | Major layout gap |
| `space-16` | 64px | Hero/page-level breathing |

**Border radius scale:**
- `rounded-sm`: 4px — badges, tags
- `rounded`: 6px — buttons, inputs, small cards
- `rounded-md`: 8px — cards, panels
- `rounded-lg`: 12px — modals, large panels
- `rounded-full`: 9999px — avatars, pill badges only

**Grid:** 12-column, `gap-6`, `max-w-7xl` container with `px-6` horizontal padding.

**Sidebar layout:** `220px` fixed sidebar + flexible main content.

**Whitespace philosophy:** Dense but not cramped. Every empty space must be intentional — not padding added to fill space, but space that makes the content easier to read. Cards breathe at 20px internal padding. Sections separate at 32px.

---

## 6. Depth & Elevation

| Level | Use | Shadow |
|-------|-----|--------|
| 0 | Canvas, flat elements | none |
| 1 | Cards, panels | `0 1px 3px rgba(0,0,0,0.3), 0 1px 0 rgba(255,255,255,0.03) inset` |
| 2 | Hover states, focused cards | `0 4px 12px rgba(0,0,0,0.4)` |
| 3 | Dropdowns, tooltips | `0 8px 24px rgba(0,0,0,0.5), 0 1px 0 rgba(255,255,255,0.06) inset` |
| 4 | Modals, command palette | `0 16px 48px rgba(0,0,0,0.6), 0 1px 0 rgba(255,255,255,0.06) inset` |
| 5 | Toasts, notifications | `0 24px 64px rgba(0,0,0,0.7)` |

Inner border highlight: `box-shadow: inset 0 1px 0 rgba(255,255,255,0.06)` on all elevated surfaces — creates edge refraction (liquid glass effect).

---

## 7. Do's and Don'ts

### Do
- Use Zinc palette (`zinc-950` → `zinc-800`) for all surfaces — already aligned with Tailwind config
- Use amber (`amber-400`, `amber-500`) as the sole accent colour
- Use status colours sparingly — only for actual states (running/passed/failed), not decoration
- Use `tabular-nums` on all numerical data
- Use `Geist Mono` for IDs, SHAs, session tokens, code, metric numbers
- Animate only `transform` and `opacity` — never `top`, `left`, `width`, `height`
- Show all four component states: default, hover, active/selected, disabled
- Build skeleton loaders for every async data surface
- Use CSS Grid for layout, not flexbox percentage math

### Don't
- No light mode components (dark-first, always)
- No Inter font — use Geist
- No purple or blue gradients — amber only
- No `border-radius` above 12px except avatars/pill badges
- No bounce easing — use `ease-out` or spring (`cubic-bezier(0.16,1,0.3,1)`)
- No centered hero layouts with three equal cards
- No placeholder text like "John Doe", "Acme Corp", "99.99% uptime"
- No inline hardcoded hex colours — use the token system above
- No decorative animations — motion must communicate state (loading, success, transition)
- No shadows lighter than level 1 on dark backgrounds — they won't be visible

---

## 8. Responsive Behavior

| Breakpoint | Width | Strategy |
|------------|-------|----------|
| `xs` | < 375px | Not targeted (app is dashboard-first) |
| `sm` | ≥ 640px | Single column, sidebar hidden (bottom nav) |
| `md` | ≥ 768px | Two-column cards, sidebar collapsed to icons |
| `lg` | ≥ 1024px | Full sidebar expanded, three-column grids |
| `xl` | ≥ 1280px | Default design target |
| `2xl` | ≥ 1536px | Max content width capped at `max-w-7xl` |

**Touch targets:** Minimum 44×44px on mobile. All icon buttons expand to 44px hit area on `sm`.

**Collapsing strategy:**
- Sidebar: `220px` expanded → `48px` icon-only at `md` → hidden (slide-up sheet) at `sm`
- Data tables: horizontal scroll with sticky first column at `sm`
- Cards: stack to single column at `sm`

---

## 9. Agent Prompt Guide

### Quick colour reference
```
Canvas: #09090b | Surface: #18181b | Accent: #f59e0b
Text: #fafafa (primary) · #a1a1aa (secondary) · #71717a (tertiary)
Border: rgba(255,255,255,0.06) default · rgba(255,255,255,0.10) strong
Status: #22c55e success · #ef4444 error · #3b82f6 info
```

### Ready-to-use component prompts

**Session card:**
> Build a session status card using DESIGN.md. Show: session ID (Geist Mono, text-tertiary), status badge (surface-1 bg, status colour text), progress phases as horizontal dots, elapsed time (tabular-nums), repository name (text-primary, truncated). Card: surface-1 bg, border-subtle, rounded-md, p-5. Hover: surface-2 bg transition 150ms.

**Build log terminal:**
> Create a streaming log terminal using DESIGN.md. Container: surface-0 bg, border-subtle, rounded-md. Scrollable with `max-h-96`. Lines: Geist Mono 13px, text-secondary. Phase headers: amber, weight 500. Error lines: status-error. Timestamps: text-tertiary tabular-nums.

**Metric stat card:**
> Build a metric card using DESIGN.md. Large number: 2.25rem Geist, weight 700, text-primary, tabular-nums. Label below: 12px, weight 500, uppercase, letter-spacing 0.06em, text-tertiary. Trend indicator: amber arrow up or red arrow down with percentage. Card: surface-1, border-subtle, rounded-md, p-5.

**Navigation sidebar item:**
> Create a sidebar nav item using DESIGN.md. Height 32px, border-radius 5px, font-size 13px. Default: transparent bg, text-tertiary. Hover: rgba(255,255,255,0.04) bg, text-secondary. Active: rgba(255,255,255,0.06) bg, text-primary, amber left-border 2px. Icon 16px left-aligned. Transition background 100ms ease.

**Linear issue badge:**
> Create a Linear issue reference badge using DESIGN.md. Format: "RA-1059". Geist Mono 11px, weight 500, text-tertiary. Bg: surface-2. Border: border-subtle. Rounded-sm. Padding 0 6px, height 18px. On hover: text-secondary, border-default.

### Iteration guide
1. Build from DESIGN.md tokens — no hardcoded hex
2. Show all states: default, hover, active, loading, empty, error
3. Test at 1280px and 375px
4. Screenshot with Playwright (`visual-qa` skill) before marking done
5. Run `npx impeccable detect src/` for anti-pattern check
