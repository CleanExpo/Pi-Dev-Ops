# Pi-CEO Supabase schema

The schema has two independently re-runnable entry points:

- [`migration.sql`](./migration.sql) — the general Pi-CEO schema.
- [`migrations/20260804190000_lessons_durable.sql`](./migrations/20260804190000_lessons_durable.sql)
  — only the durable lesson store required by RA-7111.

Both files run in their own transaction and replace policies atomically. Neither
file invokes the other or applies itself to a database.

## When to run it

- **Complete new project:** run `migration.sql` first, then the ordered
  `20260804190000_lessons_durable.sql` migration. Re-running either file is safe.
- **Add durable lessons to an existing project:** run only
  `20260804190000_lessons_durable.sql`. It preserves an existing table and rows
  created by the former bundled definition while reconciling its index, RLS and
  `service_only` policy.
- **Lessons-only sandbox or service:** the standalone migration can run against
  an otherwise empty Supabase database; it has no table dependency on
  `migration.sql`. A plain PostgreSQL fixture must first create the Supabase
  `service_role`, as the sandbox verifier does.
- **After adding another general table:** re-run `migration.sql`; idempotency
  guards existing rows.

## How to run

### Option 1 — Supabase Dashboard (fastest)

1. Open the Supabase project's SQL Editor:
   `https://supabase.com/dashboard/project/<PROJECT_REF>/sql/new`
2. Paste the contents of the required file from the ordering above.
3. Hit **Run**

### Option 2 — psql (CI / programmatic)

```bash
PGPASSWORD=$SUPABASE_DB_PASSWORD psql -X -v ON_ERROR_STOP=1 \
  "postgresql://postgres@db.<PROJECT_REF>.supabase.co:5432/postgres" \
  -f supabase/migrations/20260804190000_lessons_durable.sql
```

Use `-f supabase/migration.sql` instead when applying the general schema.
Do not use `supabase db push --include-all` to target only durable lessons: that
command can apply other pending files from `supabase/migrations/` as well.

## Rollback awareness

These are forward-only schema migrations. If application rollout is reverted,
leave `lessons_durable` and its rows in place; the unused table is harmless and
retains institutional-memory data for a later retry. Do not automate `DROP TABLE`
as rollback. Removing the table or rows is a destructive production data action
that requires a separately approved backup and operator plan.

## Which tables matter

The application is **not blocked** if Supabase is missing — every write goes
through `_insert()` in `supabase_log.py` which catches exceptions and only
WARNs. But for full observability, the tables in [CLAUDE.md → Observability]
should exist. The current state of declared-vs-written-vs-missing is documented
there.

## Adding a new table

1. Append `CREATE TABLE IF NOT EXISTS new_table (…);` to `migration.sql`
2. Append `CREATE POLICY` statements (RLS is enabled per-table in
   `migration.sql` — anon role gets no access by default).
3. Add the writer function in `supabase_log.py`.
4. Update CLAUDE.md → Observability → Tables actually written today.
5. Re-run the migration on every Supabase project that needs it (dev + prod).
