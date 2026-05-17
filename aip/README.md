# @unite-group/aip — Application Intelligence Platform

Palantir-Foundry-parallel ontology + actions layer for Unite-Group.

## Status

**Day 1 of 5 — scaffold only.** Migrations, types, and a seed-script emitter that
covers the entities surfaced by the 2026-05-11 Google Account sprawl audit.

Days 2–5 (read API, action runtime, MCP server, Wiki file-watcher) are not yet
built. Do not extend this package without re-reading the spec first.

## Canonical spec

`~/2nd Brain/2nd Brain/Wiki/aip-first-slice-schema.md`

Architectural decisions locked 2026-05-11:

1. URI scheme — `aip://unite-group/{kind}/{id}` (opaque, MCP-routed, not HTTPS-deref'able).
2. Wiki ↔ Entity bridge — frontmatter + fenced ` ```aip ` block, single-file. v1 is
   Wiki → Entity only (file-watcher ships Day-5).
3. Permission model — Supabase RLS now; `aip_grants` documented as a future upgrade
   path but **not** built yet.

## Layout

```
aip/
  src/
    types/
      primitives.ts       # Entity, Property, Relationship, Action, SourceRef, ActionContext, AuditMeta
      entities.ts         # 5 first-slice entity kinds + URI helpers
      relationships.ts    # 7 typed Relationship variants
    seed/
      audit-2026-05-11.ts # emits idempotent INSERT … ON CONFLICT DO NOTHING SQL
  package.json
  tsconfig.json
```

Migrations live alongside the rest of the Pi-Dev-Ops Postgres schema:

```
supabase/migrations/
  20260512_aip_core.sql   # aip_entities, aip_relationships, aip_action_log + RLS
  20260512_aip_views.sql  # one view per entity kind
```

## Scripts

```bash
pnpm install            # or: npm install
pnpm typecheck          # tsc --noEmit
pnpm seed > seed.sql    # emits SQL to stdout — does NOT execute against any DB
```

The seed script is **emit-only**. To apply migrations or seed data, use the normal
Supabase migration workflow once the changes have been reviewed.
