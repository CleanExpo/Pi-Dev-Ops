# Pi-CEO Supabase schema

Single migration file: [`migration.sql`](./migration.sql) — 252 lines, all
`CREATE TABLE IF NOT EXISTS …` so it's safe to re-run any number of times.

## When to run it

- **First deploy to a new Supabase project** — required, otherwise the few
  fire-and-forget logger calls in `supabase_log.py` will warn-and-skip on
  every invocation (non-fatal but noisy).
- **After adding a new table** to the migration — re-run; idempotency guards
  the existing rows.

## How to run

### Option 1 — Supabase Dashboard (fastest)

1. Open the Supabase project's SQL Editor:
   `https://supabase.com/dashboard/project/<PROJECT_REF>/sql/new`
2. Paste the contents of `migration.sql`
3. Hit **Run**

### Option 2 — Supabase MCP / CLI

```bash
# Via supabase CLI (assumes `supabase login` done)
supabase db push --include-all --project-ref <PROJECT_REF>
```

### Option 3 — psql (CI / programmatic)

```bash
PGPASSWORD=$SUPABASE_DB_PASSWORD psql \
  "postgresql://postgres@db.<PROJECT_REF>.supabase.co:5432/postgres" \
  -f supabase/migration.sql
```

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
