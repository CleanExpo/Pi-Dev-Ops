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

## Anti-Patterns to Flag

When reviewing a DESIGN.md or a design brief, flag these:
- No semantic token system (hardcoded hex throughout)
- Missing monospace font for data/code
- Missing status colours (how do error/success/warning states look?)
- No `Do's and Don'ts` section (means design decisions will be inconsistent)
- Missing responsive strategy
- No Agent Prompt Guide section (agents can't use the design system efficiently)
