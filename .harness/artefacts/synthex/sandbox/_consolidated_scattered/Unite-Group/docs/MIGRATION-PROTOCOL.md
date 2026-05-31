# Synthex Migration Protocol

All Supabase schema changes must go through this protocol. No migration may be applied directly to production.

## The Rule

> **No direct production pushes.** Every migration runs through `scripts/safe-migrate.sh`, which previews on a branch and requires an explicit `yes` to apply to production.

## Quick Start

```bash
# Set your Supabase access token (once per terminal session)
export SUPABASE_ACCESS_TOKEN=<your-token>
# Get a token at: https://supabase.com/dashboard/account/tokens

# Preview migration on a branch (no production changes)
./scripts/safe-migrate.sh supabase/migrations/20260401_your_migration.sql

# Dry run (prints what would happen, touches nothing)
./scripts/safe-migrate.sh supabase/migrations/20260401_your_migration.sql --dry-run
```

## What safe-migrate.sh Does

| Step | Action |
|------|--------|
| 1 | Validates `SUPABASE_ACCESS_TOKEN` — fails immediately if missing |
| 2 | Scans SQL for destructive patterns (`DROP TABLE`, `TRUNCATE`, etc.) and warns |
| 3 | Creates an isolated Supabase DB branch |
| 4 | Applies the migration to the branch |
| 5 | Validates the branch is healthy |
| 6 | Prompts human: type `yes` to apply to production — anything else aborts |

Only exact `yes` input applies to production. Branch is deleted after confirmation or abort.

## Migration File Conventions

Filename format: `supabase/migrations/YYYYMMDDHHMMSS_description.sql`

```
supabase/migrations/
  20260401120000_add_geo_citation_events.sql
  20260401130000_add_recommended_actions.sql
```

### Required SQL conventions

- Every `CREATE TABLE` must use `IF NOT EXISTS`
- Every `ALTER TABLE ADD COLUMN` must use `IF NOT EXISTS`
- Every `DROP INDEX` must use `IF EXISTS`
- Include a `-- Description:` comment at the top of every migration file
- New tables require RLS: `ALTER TABLE x ENABLE ROW LEVEL SECURITY;`

### Template

```sql
-- Description: <what this migration does and why>
-- Author: <name>
-- Date: YYYY-MM-DD
-- Linear: SYN-XXX

BEGIN;

-- Your migration here
CREATE TABLE IF NOT EXISTS public.your_table (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.your_table ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_all" ON public.your_table
  FOR ALL TO service_role USING (true) WITH CHECK (true);

COMMIT;
```

## After a Migration

1. Regenerate TypeScript types:
   ```bash
   npm run gen:types
   ```
2. Commit the updated `types/supabase.ts` in the same PR as the migration.
3. CI will fail on the next PR if `types/supabase.ts` is out of sync with the live schema (drift check).

## Emergency Rollback

If a production migration causes an incident:

1. Assess impact — check Supabase logs
2. If a column/table was added: it is safe to drop in a new migration
3. If data was modified: restore from the most recent Supabase point-in-time backup
4. Never attempt manual SQL rollback without checking with the team first

## Who Can Run Migrations

- Developers with `SUPABASE_ACCESS_TOKEN` for the Synthex project
- CI/CD does NOT run migrations automatically — only humans run `safe-migrate.sh`
- SYN-583 (ML metadata columns) must run through this process before Sprint 4 RBAC work

## Related

- `scripts/safe-migrate.sh` — the migration runner
- `npm run gen:types` — regenerate TypeScript types after schema change
- `npm run check:schema-drift` — check if types are in sync with live schema
- SYN-589 — Linear issue tracking this protocol
