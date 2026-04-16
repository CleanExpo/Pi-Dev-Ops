---
name: ui-component-builder
description: Senior-level UI implementation skill. Generates multi-variant React/Tailwind components grounded in DESIGN.md, applies taste-skill quality constraints (banning AI-default slop), and uses 21st.dev Magic patterns for component discovery and generation.
automation: manual
intents: design, feature
---

# UI Component Builder Skill

Builds production-quality React components that match the project's DESIGN.md exactly.
Always generates 3 variants, always shows all interaction states, never ships a
component without a loading skeleton and empty state.

**Always read `DESIGN.md` before building anything.**

---

## The 3-Dial System

Before building, set these three dials based on the component's context:

| Dial | Range | Low (1–3) | Mid (4–6) | High (7–10) |
|------|-------|-----------|-----------|-------------|
| `DESIGN_VARIANCE` | Layout complexity | Symmetric/centered | Asymmetric sections | Masonry/fractional grids |
| `MOTION_INTENSITY` | Animation richness | Hover only (opacity) | Scroll-triggered reveals | Spring physics, magnetic |
| `VISUAL_DENSITY` | Information density | Art gallery / airy | Standard dashboard | Cockpit / data terminal |

For Pi-CEO dashboard components: `DESIGN_VARIANCE=3`, `MOTION_INTENSITY=4`, `VISUAL_DENSITY=7`
For landing pages: `DESIGN_VARIANCE=6`, `MOTION_INTENSITY=6`, `VISUAL_DENSITY=3`
For admin/settings: `DESIGN_VARIANCE=2`, `MOTION_INTENSITY=2`, `VISUAL_DENSITY=5`

---

## Mandatory Quality Rules

### Font rules
- **Never use Inter.** Use `Geist` (Pi-CEO) or whatever the DESIGN.md specifies.
- **Never use system-ui as the primary font** in generated components (it shows different on every OS).
- Monospace data (IDs, hashes, scores, metrics): always use the DESIGN.md mono font.

### Colour rules
- **Never output hex codes directly in component JSX.** Use Tailwind tokens or CSS variables from DESIGN.md.
- **Never use purple or blue gradients** unless the DESIGN.md explicitly defines them.
- **Never use generic `bg-gray-`** — use the specific surface tokens from DESIGN.md.

### Layout rules
- **CSS Grid over flexbox percentage math.** Use `grid-cols-*` not `flex: 0 0 33%`.
- **Never build a 3-equal-card grid as the top-level hero section layout.**
- **Never center the entire page layout** when `DESIGN_VARIANCE > 4`.
- Spacing: use the DESIGN.md spacing scale. Never `mt-7` or `px-3.5` (off-scale values).

### Motion rules
- **Only animate `transform` and `opacity`.** Never animate `top`, `left`, `width`, `height`.
- **Never use `bounce` easing.** Use `ease-out` or spring: `cubic-bezier(0.16, 1, 0.3, 1)`.
- Use Framer Motion `useMotionValue` for magnetic effects, not `useState`.
- Respect `prefers-reduced-motion` — wrap all non-essential animations.

### Content rules
- **Never use "John Doe", "Acme Corp", "99.99%", "SmartFlow", "Project Alpha".**
- Use realistic, organic-sounding data: real-looking names, plausible metrics, genuine repo names.
- **Never use placeholder comment `// TODO: implement`** — build the real thing or omit.

---

## Mandatory States (every component ships with all of these)

| State | Required |
|-------|----------|
| Default | ✅ Always |
| Hover | ✅ Always |
| Active / Selected | ✅ Always |
| Loading (skeleton) | ✅ Always for async data |
| Empty | ✅ Always for list/collection components |
| Error | ✅ Always for data-fetching components |
| Disabled | ✅ When action can be disabled |
| Focus (keyboard) | ✅ Always — visible focus ring |

### Skeleton pattern
```tsx
// Always build skeletal loading, never spinners for content areas
<div className="animate-pulse space-y-3">
  <div className="h-4 bg-zinc-800 rounded w-3/4" />
  <div className="h-4 bg-zinc-800 rounded w-1/2" />
</div>
```

### Liquid glass (elevated surfaces)
```css
/* Apply to cards, modals, dropdowns */
backdrop-filter: blur(12px);
background: rgba(24, 24, 27, 0.8);
border: 1px solid rgba(255, 255, 255, 0.06);
box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08); /* edge refraction */
```

---

## 21st.dev Magic Patterns

For component inspiration before building from scratch:
```bash
# Install the MCP server (gives Claude Code a /ui command)
npx @21st-dev/cli@latest install claude --api-key YOUR_KEY
```

Component categories available in the 21st.dev library:
- **Agentic UI:** Agent plan visualizer, message dock, streaming indicator, progress pipeline with node activation
- **Data flow:** Animated data packets, progress steps, bounding box selector
- **Hero/marketing:** Device assembly, kinetic type mask, frosted glass wipe, spatial push
- **Standard:** Pricing tables, feature grids, testimonials, CTA sections

**Workflow:** Use `21st_magic_component_inspiration` (semantic search) first to find closest existing pattern → then build with `21st_magic_component_builder` to generate 3–5 style variants → pick one → adapt to DESIGN.md tokens.

---

## Pi-CEO Specific Component Patterns

### Build session card
```tsx
// Status badge using DESIGN.md status tokens
const statusConfig = {
  running:  { label: 'Running',  class: 'bg-blue-500/10 text-blue-400' },
  complete: { label: 'Done',     class: 'bg-green-500/10 text-green-400' },
  failed:   { label: 'Failed',   class: 'bg-red-500/10 text-red-400' },
  killed:   { label: 'Killed',   class: 'bg-zinc-500/10 text-zinc-400' },
}
```

### Phase progress indicator
```tsx
// Horizontal phase dots — not a progress bar
const phases = ['clone', 'scan', 'plan', 'build', 'eval', 'push']
// Active: amber dot with pulse ring
// Done: solid zinc dot
// Pending: empty dot with border
```

### Streaming log terminal
```tsx
// Fixed-height, overflow-y-auto, scroll-to-bottom on new content
// Phase headers: amber colour, weight 500
// Error lines: red (status-error)
// Timestamps: Geist Mono, text-tertiary, right-aligned
```

### Metric stat (score, token count, duration)
```tsx
// Large number: 2.25rem, weight 700, tabular-nums
// Delta indicator: amber arrow (up) or red arrow (down)
// Label: 11px, weight 500, uppercase, letter-spacing 0.06em, text-tertiary
```

---

## npxskillui — Extract Any Design System

```bash
# From a live URL
npx skillui --url https://app.your-reference.com --mode ultra

# From an existing codebase directory
npx skillui --dir ./src --mode ultra

# From a public GitHub repo
npx skillui --repo owner/repo --mode ultra
```

Output: `SKILL.md`, `CLAUDE.md`, `DESIGN.md`, `ANIMATIONS.md`, `COMPONENTS.md`,
`tokens/colors.json`, `tokens/typography.json`, `tokens/spacing.json`, `screens/`

After running, read the output and validate against the live site before using the tokens.

---

## Output Checklist (before marking a component done)

- [ ] Read DESIGN.md — used correct fonts, colours, spacing scale
- [ ] All 4+ states implemented (default, hover, active, disabled/error)
- [ ] Skeleton loader built for async data surfaces
- [ ] Only `transform` + `opacity` animated
- [ ] `prefers-reduced-motion` wrapped on animations
- [ ] No hardcoded hex values — only Tailwind classes or CSS variables
- [ ] No placeholder content ("John Doe", "Acme", etc.)
- [ ] Accessible: keyboard navigable, visible focus ring, ARIA labels on icon buttons
- [ ] Responsive: tested at `sm` (375px) and `xl` (1280px)
- [ ] Export: named export, TypeScript props interface, no default export
