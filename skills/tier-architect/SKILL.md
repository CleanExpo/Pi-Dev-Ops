---
name: tier-architect
description: Design tier configurations - which models for which roles.
---

# Tier Architect

Design the tier hierarchy for your project.

## Tier Config Format (YAML)
tiers:
  - name: orchestrator
    model: opus
    role: Plans and coordinates
  - name: specialist
    model: sonnet
    parent: orchestrator
    role: Complex implementation
  - name: worker
    model: haiku
    parent: specialist
    role: Discrete tasks

## Cold-start context (RA-1968)

- On cold-start, check for `<dir>/WIKI.md` files alongside SKILL.md/CLAUDE.md and read them to seed context. Each `WIKI.md` is auto-refreshed post-merge by `tao-codebase-wiki` (`app/server/tao_codebase_wiki.py`).
