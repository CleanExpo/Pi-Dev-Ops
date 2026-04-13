---
name: design-system
description: Bootstrap or extend a component design system using Tailwind + shadcn/ui patterns for Pi-CEO's Next.js dashboard.
automation: manual
anthropic_skill: anthropic-skills:design-system-to-production-quick-start
intents: design, feature
---

# Design System Skill

Scaffolds consistent UI components, tokens, and patterns for Pi-CEO's
Next.js 16 + Tailwind CSS dashboard. Uses the Anthropic Cloud Skill
`anthropic-skills:design-system-to-production-quick-start` for production-ready output.

## When to use

- Adding new dashboard pages or panels
- Ensuring a new component matches existing colour/spacing tokens
- Migrating ad-hoc styles to the design system

## Stack

- Next.js 16.2.2 + React 19
- Tailwind CSS (config in `dashboard/tailwind.config.ts`)
- Component conventions: `dashboard/components/`
- Tokens: defined in `dashboard/lib/theme.ts` (or equivalent)

## Usage

Invoke via the Skill tool or reference in a brief:

```
Use the design-system skill to build a StatusBadge component that shows
build status with colour-coded variants: running (blue), passed (green),
failed (red), warned (yellow).
```

## Constraints

- Match existing component naming conventions (`PascalCase`)
- Import tokens from the shared theme; do not hardcode hex colours
- Components must be server-renderable by default (no `"use client"` unless needed)
