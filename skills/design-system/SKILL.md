---
name: design-system
description: Design stack orchestrator for Pi-CEO. Routes UI work to the correct specialist skill (design-intelligence, ui-component-builder, design-audit, visual-qa). Start here for any design task.
automation: manual
intents: design, feature
---

# Design System Skill

The entry point for all UI work in the Unite-Group Nexus. This skill does not build components directly — it routes to the correct specialist and ensures every design decision is grounded in `DESIGN.md`.

**The four-layer design stack:**

| Layer | Skill | When |
|-------|-------|------|
| 1. Context | `design-intelligence` | Start of any UI work — read/create DESIGN.md |
| 2. Build | `ui-component-builder` | Building or updating React components |
| 3. Audit | `design-audit` | Before marking any component done |
| 4. Verify | `visual-qa` | After build — screenshot + regression check |

---

## Quick Routing Guide

**"Build me a [component]"**
→ `design-intelligence` (read DESIGN.md) → `ui-component-builder` (generate 3 variants) → `design-audit` (/audit) → `visual-qa` (screenshot matrix)

**"Does this look right?"**
→ `design-audit` (/critique) — UX + visual review, no edits

**"Make this better"**
→ `design-audit` (/polish) — targeted improvements, or (/bolder) for more presence

**"Match the look of [brand/site]"**
→ `design-intelligence` (reference brand archetypes, run npxskillui) → update DESIGN.md

**"Check for visual regressions"**
→ `visual-qa` — run screenshot matrix, diff against baselines

---

## Project Design Tokens (summary)

Defined in full at `Pi-Dev-Ops/DESIGN.md`. Key values for quick reference:

```
Canvas:    #09090b   Surface-1: #18181b   Surface-2: #27272a
Accent:    #f59e0b   (amber — only accent colour)
Text:      #fafafa (primary) · #a1a1aa (secondary) · #71717a (tertiary)
Border:    rgba(255,255,255,0.06) subtle · rgba(255,255,255,0.10) default
Font:      Geist (UI) + Geist Mono (data/code/IDs)
Status:    #22c55e success · #ef4444 error · #3b82f6 info · #f59e0b warning
```

---

## Stack Requirements

- `DESIGN.md` must exist in the project root before any UI work starts
- Run `npx impeccable detect src/` after every component build to catch anti-patterns
- Visual baselines must be generated on Linux (CI), not macOS — font hinting differs

---

## What This Skill No Longer Does

The old `design-system` skill referenced `anthropic-skills:design-system-to-production-quick-start`
and generic shadcn/ui scaffolding. That is retired. The Nexus design stack is now:
- Token-first (DESIGN.md → Tailwind CSS variables)
- OKLCH colour evaluation (not HSL)
- Anti-pattern detection (impeccable 24-pattern set)
- Visual regression CI (Playwright, always Linux)
- Brand archetype grounded (getdesign.md + 66 references)
