---
name: design-intelligence
description: Master design context skill. Reads/writes DESIGN.md, references 66 brand archetypes from getdesign.md, reverse-engineers any design system from a live site using npxskillui, and ensures every UI decision is grounded in explicit design intent rather than AI defaults.
automation: manual
intents: design, feature
---

# Design Intelligence Skill

The context layer of the design stack. Every other design skill depends on this one.
This skill reads the project's `DESIGN.md`, reasons about design decisions, and can
create or update the design system document from scratch if none exists.

---

## Core Responsibilities

1. **Read DESIGN.md before any UI work.** If no `DESIGN.md` exists in the project root, create one (see *Bootstrap* below).
2. **Reference brand archetypes** from the getdesign.md library (66 brands) when the user wants to match a specific aesthetic.
3. **Reverse-engineer any live site** using `npxskillui` to extract design tokens.
4. **Write and maintain DESIGN.md** as the authoritative design system document.

---

## DESIGN.md Standard Format (9 sections — always produce all 9)

1. **Visual Theme & Atmosphere** — mood, philosophy, 5-word character statement
2. **Color Palette & Roles** — semantic token table with hex + rgba values
3. **Typography Rules** — font stack + full hierarchy table (Display → Caption → Mono)
4. **Component Stylings** — buttons (all variants), cards, inputs, badges, nav, code blocks
5. **Layout Principles** — spacing scale, grid, border-radius scale, whitespace philosophy
6. **Depth & Elevation** — 6-level shadow table with exact CSS values
7. **Do's and Don'ts** — 8+ rules per column, specific and concrete
8. **Responsive Behavior** — breakpoint table, touch targets, collapsing strategy
9. **Agent Prompt Guide** — quick colour reference + 5 copy-paste component prompts

---

## Brand Archetype Library

When a user says "make this look like X", reference these design patterns:

### Nearest to Pi-CEO
| Brand | Aesthetic | Key tokens |
|-------|-----------|-----------|
| **Vercel** | Black/white precision, Geist font, zero decoration | `#000` canvas, Inter/Geist, white text |
| **Linear** | Ultra-minimal, purple accent, Berkeley Mono | `#08090a` canvas, `#5e6ad2` accent |
| **Supabase** | Dark emerald, code-first, developer density | `#1c1c1c` canvas, `#3ecf8e` accent |
| **Raycast** | Sleek dark chrome, vibrant gradients | Dark chrome, gradient accents |
| **Warp** | IDE-like dark, block-based command UI | Terminal dark, monospace-first |

### Premium / Enterprise
| Brand | Aesthetic |
|-------|-----------|
| **Stripe** | Purple gradients, weight-300 elegance, pristine white |
| **Apple** | Premium whitespace, SF Pro, cinematic imagery |
| **IBM** | Carbon system, structured blue, enterprise grid |
| **Superhuman** | Purple glow, keyboard-first, ultra-premium dark |

### Developer Tools
| Brand | Aesthetic |
|-------|-----------|
| **Cursor** | Sleek dark, gradient accents |
| **Sentry** | Dark dashboard, data-dense, pink-purple |
| **PostHog** | Playful dark, developer-friendly |
| **Ollama** | Terminal-first, monochrome simplicity |

### Fintech / Data
| Brand | Aesthetic |
|-------|-----------|
| **Revolut** | Sleek dark, gradient cards, fintech precision |
| **Coinbase** | Clean blue, institutional trust |
| **Kraken** | Purple dark, data-dense dashboards |

---

## Bootstrap: Creating a DESIGN.md for a New Project

If no `DESIGN.md` exists, run this process:

### Step 1 — Gather context (ask these 4 questions)
1. What is the primary user? (developer / executive / consumer)
2. What 3 words describe the brand personality?
3. Is there an existing codebase? If yes, what colours/fonts are already in use?
4. Which brand archetype is closest? (show the table above)

### Step 2 — Reverse-engineer existing code (if codebase exists)
```bash
npx skillui --dir ./dashboard --mode ultra
```
This extracts: CSS variables, Tailwind config tokens, component patterns, animation specs.
Read the generated `DESIGN.md` output and validate against the actual codebase.

### Step 3 — Reverse-engineer a reference site (if no codebase)
```bash
npx skillui --url https://linear.app --mode ultra
# Produces: DESIGN.md, ANIMATIONS.md, COMPONENTS.md, tokens/colors.json, tokens/typography.json
```

### Step 4 — Compose the DESIGN.md
Produce all 9 sections. Use the tokens extracted in Step 2–3 as the foundation.
Apply the brand archetype patterns from Step 1 as the aesthetic guide.

---

## Updating an Existing DESIGN.md

When the design evolves, update these sections in order:
1. Color Palette (if new colours added)
2. Component Stylings (if new component types added)
3. Do's and Don'ts (if new anti-patterns discovered)
4. Agent Prompt Guide (add prompts for new component types)

Always bump the `_Updated` date at the top of the file.

---

## Working with getdesign.md

Install any brand's DESIGN.md as a reference:
```bash
npx getdesign@latest add linear.app       # Linear design system
npx getdesign@latest add stripe            # Stripe design system
npx getdesign@latest add vercel            # Vercel design system
```

Use reference files as: `@.design-references/linear.app.md` in briefs to tell the
component builder to match that aesthetic for specific pages or sections.

---

## DESIGN.md from a screenshot (vision path)

When there is no codebase and no live URL — only an image of a design you like — build the
DESIGN.md by reading the screenshot directly:

1. Read the image. Name the palette (sample the actual pixels, don't guess), the type
   hierarchy, spacing rhythm, and elevation.
2. Produce all 9 DESIGN.md sections from what is observed, not from defaults.
3. Emit a single self-contained `preview.html` that renders the tokens (swatches, type
   scale, one of each component) so the extraction is visually checkable before any real UI
   is built.

## Reverse-engineer a live site → reusable skill (one-shot)

Beyond extracting a one-off DESIGN.md, bottle a reference aesthetic into a *reusable* skill
so every future build inherits it:

```bash
npx skillui --url https://linear.app --mode ultra --emit-skill
```

This produces a `SKILL.md` (name, description, trigger, the extracted tokens as the
procedure) — not just a document. Register it in the router so "make it feel like Linear"
routes to a grounded skill instead of re-scraping. One reference site → one durable skill.

## Design laws — the taste layer

The kit guarantees the floor; taste raises the ceiling. Grounding a build in tokens stops
AI-default slop only if these laws hold:

- **OKLCH, not raw hex.** Author colour in OKLCH so lightness/chroma stay perceptually even
  across a ramp; convert to hex at output only.
- **Never pure `#000` / `#fff`.** Use a near-black and a warm off-white — pure values read as
  unfinished and vibrate against each other.
- **One accent, used with restraint.** A single accent, applied sparingly, reads as
  intentional; two or more accents read as a template.
- **Theme from the scene.** Pull the palette from the hero image/content, not from a swatch
  picker — the page and its imagery must share one light.
- **No em dashes in display copy.** They read as machine-written in headlines.
- **Anti-slop bans** (flag on sight): the gradient blob background, three identical feature
  cards, the stock team-photo grid, floating geometric shapes, the generic purple→blue AI
  gradient.

## Scroll & motion styles (for animated / 3D sites)

When a brief calls for a scroll-driven or 3D site, name the motion style up front — pick one,
don't blend:

| Style | Motion |
|-------|--------|
| **A — Loop** | Hero animation loops seamlessly; alive at rest, never freezes |
| **B — Scrub** | Scroll position scrubs a timeline (frames, not mp4 — WebP frames scrub smoother) |
| **C — Cursor** | Elements react to cursor position |
| **D — Horizontal** | Vertical scroll drives horizontal travel |
| **E — Exploded** | Parts assemble/disassemble on scroll |
| **F — Push-through** | Camera pushes through layered planes |
| **G — Scrollytelling** | Copy beats pinned to scroll milestones |

Motion render laws: locked camera, constant velocity, motion-blur off, `START = END` for any
loop. A frozen hero reads as broken.

---

## Anti-Patterns to Flag

When reviewing a DESIGN.md or a design brief, flag these:
- No semantic token system (hardcoded hex throughout)
- Missing monospace font for data/code
- Missing status colours (how do error/success/warning states look?)
- No `Do's and Don'ts` section (means design decisions will be inconsistent)
- Missing responsive strategy
- No Agent Prompt Guide section (agents can't use the design system efficiently)
