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
- Candy depth on gun-metal. Saturated reds, oranges, greens (+ cyan/amber complements) carry signal — layered over a near-black base. Never a flat `#000` or `#fff` dead-space fill, never purple.

**Atmosphere keywords:** gun-metal precision · terminal authority · candy-bright signal · Geist clarity · zero-touch confidence

---

## 2. Color Palette & Roles

> **Base rule (Phill):** black base, candy depth on top. Empty/dead space is never pure white (`#ffffff`) or dead black (`#000000`) — it uses the tinted gun-metal surface ramp below and off-white text. Colour sits on top of the dark base like a candy coat; the base itself carries depth, not a flat void fill.

### Surfaces (gun-metal ramp)
| Token | Hex | Role |
|-------|-----|------|
| `canvas` | `#0e1014` | Page background — gun-metal near-black (never `#000`) |
| `surface-0` | `#13161c` | Sidebar, primary panels |
| `surface-1` | `#191e26` | Cards, modals, elevated panels |
| `surface-2` | `#232934` | Hover states, selected rows, code blocks |
| `surface-3` | `#2e3542` | Active states, strong separators |

### Borders
| Token | Value | Role |
|-------|-------|------|
| `border-subtle` | `rgba(255,255,255,0.06)` | Default card/panel border |
| `border-default` | `rgba(255,255,255,0.10)` | Input borders, dividers |
| `border-strong` | `rgba(255,255,255,0.18)` | Focus rings, active states |

### Brand & Accent (Candy Red — CEO action)
| Token | Hex | Role |
|-------|-----|------|
| `brand` | `#ff3b5c` | Primary CTA, links, key metrics, badges — the CEO-action candy red |
| `brand-dim` | `rgba(255,59,92,0.14)` | Candy-red tint backgrounds |
| `brand-hover` | `#ff5c77` | Button hover, link hover |

### Text (off-white — never pure `#ffffff`)
| Token | Value | Role |
|-------|-------|------|
| `text-primary` | `#f4f5f7` | Headings, primary content |
| `text-secondary` | `#a7adba` | Labels, meta, secondary content |
| `text-tertiary` | `#727a88` | Placeholder, disabled, timestamps |
| `text-disabled` | `#4d535f` | Truly disabled elements |
| `text-inverse` | `#0e1014` | Text on candy (red/orange/green) backgrounds |

### Status & Supplementary Candy Hues
| Token | Hex | Role |
|-------|-----|------|
| `status-success` | `#00d97e` | Candy green — complete, passed, healthy |
| `status-warning` | `#ff8a1f` | Candy orange — warning, in-review |
| `status-error` | `#e5484d` | Alarm red — failed, critical (flatter than brand candy red, kept distinct) |
| `status-info` | `#22d3ee` | Candy cyan — running, in-progress (cool complement) |
| `accent-amber` | `#ffb020` | Candy amber — secondary signal, highlights |
| `status-neutral` | `#727a88` | Killed, cancelled, unknown |

### Status tints (for badges)
```css
.badge-success { background: rgba(0,217,126,0.12);  color: #00d97e; }
.badge-error   { background: rgba(229,72,77,0.12);   color: #e5484d; }
.badge-warning { background: rgba(255,138,31,0.12);  color: #ff8a1f; }
.badge-info    { background: rgba(34,211,238,0.12);  color: #22d3ee; }
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

**Primary (candy-red CTA)**
```css
background: #ff3b5c;
color: #0e1014;
font-weight: 500;
font-size: 14px;
height: 36px;
padding: 0 16px;
border-radius: 6px;
border: none;
transition: background 150ms ease;
/* hover */ background: #ff5c77;
/* active */ transform: scale(0.98);
/* disabled */ opacity: 0.4; cursor: not-allowed;
```

**Secondary (ghost)**
```css
background: transparent;
color: #f4f5f7;
border: 1px solid rgba(255,255,255,0.10);
height: 36px;
padding: 0 16px;
border-radius: 6px;
/* hover */ background: rgba(255,255,255,0.05); border-color: rgba(255,255,255,0.18);
/* active */ transform: scale(0.98);
```

**Destructive**
```css
background: rgba(229,72,77,0.12);
color: #e5484d;
border: 1px solid rgba(229,72,77,0.25);
/* hover */ background: rgba(229,72,77,0.20);
```

**Icon button**
```css
width: 36px; height: 36px;
border-radius: 6px;
background: transparent;
color: #727a88;
/* hover */ background: rgba(255,255,255,0.06); color: #f4f5f7;
```

### Cards / Panels
```css
background: #191e26;
border: 1px solid rgba(255,255,255,0.06);
border-radius: 8px;
padding: 20px;
/* elevated (modal, popover) */
box-shadow: 0 8px 24px rgba(0,0,0,0.4), 0 1px 0 rgba(255,255,255,0.04) inset;
```

### Inputs & Text Fields
```css
background: #0e1014;
border: 1px solid rgba(255,255,255,0.10);
border-radius: 6px;
height: 36px;
padding: 0 12px;
color: #f4f5f7;
font-size: 14px;
/* focus */
border-color: rgba(255,255,255,0.25);
outline: 2px solid rgba(255,59,92,0.25);
outline-offset: 0;
/* error */
border-color: rgba(229,72,77,0.50);
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
background: #13161c;
border-right: 1px solid rgba(255,255,255,0.06);
/* Nav item */
height: 32px;
padding: 0 12px;
border-radius: 5px;
font-size: 13px;
color: #727a88;
/* active */ background: rgba(255,255,255,0.06); color: #f4f5f7; border-left: 2px solid #ff3b5c;
/* hover */ background: rgba(255,255,255,0.04); color: #a7adba;
```

### Code / Terminal Blocks
```css
background: #13161c;
border: 1px solid rgba(255,255,255,0.06);
border-radius: 6px;
padding: 16px;
font-family: 'Geist Mono', monospace;
font-size: 13px;
line-height: 1.6;
color: #a7adba;
/* keyword */ color: #ff8a1f;
/* string */  color: #00d97e;
/* comment */ color: #4d535f;
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
- Use the gun-metal surface ramp (`canvas` → `surface-3`) for all backgrounds — tinted near-black, never flat `#000`
- Use candy red (`#ff3b5c`) as the primary action accent; greens, oranges, cyan and amber are signal hues — applied to actual state, not decoration
- Layer candy depth on top of the dark base — the colour pops because the base is restrained
- Use `tabular-nums` on all numerical data
- Use `Geist Mono` for IDs, SHAs, session tokens, code, metric numbers
- Animate only `transform` and `opacity` — never `top`, `left`, `width`, `height`
- Show all four component states: default, hover, active/selected, disabled
- Build skeleton loaders for every async data surface
- Use CSS Grid for layout, not flexbox percentage math

### Don't
- No pure `#ffffff` fills or `#000000` fills anywhere — dead/empty space uses tinted gun-metal surfaces and off-white text
- No light mode components (dark-first, always)
- No Inter font — use Geist
- No purple. No flat neon. Candy hues stay on the warm trio (red/orange/green) plus the cyan/amber complements
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
Canvas: #0e1014 | Surface: #191e26 | Accent (candy red): #ff3b5c
Text: #f4f5f7 (primary) · #a7adba (secondary) · #727a88 (tertiary)
Border: rgba(255,255,255,0.06) default · rgba(255,255,255,0.10) strong
Status: #00d97e success · #e5484d error · #ff8a1f warning · #22d3ee info
Never: #ffffff or #000000 fills.
```

### Ready-to-use component prompts

**Session card:**
> Build a session status card using DESIGN.md. Show: session ID (Geist Mono, text-tertiary), status badge (surface-1 bg, status colour text), progress phases as horizontal dots, elapsed time (tabular-nums), repository name (text-primary, truncated). Card: surface-1 bg, border-subtle, rounded-md, p-5. Hover: surface-2 bg transition 150ms.

**Build log terminal:**
> Create a streaming log terminal using DESIGN.md. Container: surface-0 bg, border-subtle, rounded-md. Scrollable with `max-h-96`. Lines: Geist Mono 13px, text-secondary. Phase headers: candy red, weight 500. Error lines: status-error. Timestamps: text-tertiary tabular-nums.

**Metric stat card:**
> Build a metric card using DESIGN.md. Large number: 2.25rem Geist, weight 700, text-primary, tabular-nums. Label below: 12px, weight 500, uppercase, letter-spacing 0.06em, text-tertiary. Trend indicator: candy-green arrow up or alarm-red arrow down with percentage. Card: surface-1, border-subtle, rounded-md, p-5.

**Navigation sidebar item:**
> Create a sidebar nav item using DESIGN.md. Height 32px, border-radius 5px, font-size 13px. Default: transparent bg, text-tertiary. Hover: rgba(255,255,255,0.04) bg, text-secondary. Active: rgba(255,255,255,0.06) bg, text-primary, candy-red left-border 2px. Icon 16px left-aligned. Transition background 100ms ease.

**Linear issue badge:**
> Create a Linear issue reference badge using DESIGN.md. Format: "RA-1059". Geist Mono 11px, weight 500, text-tertiary. Bg: surface-2. Border: border-subtle. Rounded-sm. Padding 0 6px, height 18px. On hover: text-secondary, border-default.

### Iteration guide
1. Build from DESIGN.md tokens — no hardcoded hex
2. Show all states: default, hover, active, loading, empty, error
3. Test at 1280px and 375px
4. Screenshot with Playwright (`visual-qa` skill) before marking done
5. Run `npx impeccable detect src/` for anti-pattern check
