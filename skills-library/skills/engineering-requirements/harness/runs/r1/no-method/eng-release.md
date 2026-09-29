by: eng-release
contributed: [eng-release]
categories:
  migration:     {state: PRESCRIBED, ref: "#migration-003-is-merged-and-not-applied", by: eng-release, blocking: true}
  rollback:      {state: PRESCRIBED, ref: "#no-down-path-exists-for-003", by: eng-release, blocking: true}
  observability: {state: PRESCRIBED, ref: "#nothing-observes-whether-the-deploy-took", by: eng-release, blocking: true}
cross_domain:
  - "in the schema that is actually deployed, anon still holds SELECT/INSERT/UPDATE/DELETE on public.reports under a USING (true) policy — eng-authz owns whether that is the live tenancy hole"
  - "003 filters on public.user_tenant_access, a table no migration in this repo creates — eng-data owns whether that table is meant to exist and where it is defined"
  - "vitest.config.ts includes only lib/**/__tests__/** and app/**/__tests__/**, while the sole test file is at __tests__/engine.test.ts, so the suite that is supposed to gate the classification engine collects zero files — eng-test owns it"
  - "there is no package.json, lockfile or CI file anywhere in the tree, so nothing pins what a build would install — eng-supply-chain owns it"

## Migration 003 is merged and not applied

The ledger stops at 002. `supabase/APPLIED_LEDGER.txt:1-2` is the entire file:

```
001
002
```

`supabase/migrations/` contains three files, `003_rls_fix.sql` among them. [VERIFIED] — `ls supabase/migrations` returns `001_init.sql 002_policies.sql 003_rls_fix.sql`; the ledger's last line is `002`.

So the schema that is running is the one 002 left behind. `supabase/migrations/002_policies.sql:3-4`:

```
CREATE POLICY "Anon read access" ON public.reports
  FOR SELECT USING (true);
```

and `002_policies.sql:6`:

```
GRANT SELECT, INSERT, UPDATE, DELETE ON public.reports TO anon, authenticated;
```

The spec's gate — "Tenants must not read each other's reports" — is satisfied only by the file that never ran. Merging 003 changed the repository and nothing else. This is the exact shape of the failure: `git log` shows the fix, the running database does not.

Worse, 003 cannot apply as written. `supabase/migrations/003_rls_fix.sql:6`:

```
  USING (tenant_id IN (SELECT tenant_id FROM public.user_tenant_access WHERE user_id = auth.uid()));
```

[VERIFIED] `grep -rn "user_tenant_access" .` returns exactly one hit, that line. No migration creates the table. `CREATE POLICY` resolves its `USING` expression at creation time, so this statement errors with `relation "public.user_tenant_access" does not exist`. Two outcomes, both bad and neither loud:

- the runner wraps the file in a transaction: 003 rolls back whole, the permissive policy survives, the ledger stays at 002, and the next deploy retries the same failure forever;
- the runner does not: `DROP POLICY IF EXISTS "Anon read access"` on line 2 commits, the `CREATE POLICY` fails, and `REVOKE ALL ON public.reports FROM anon` on line 8 never runs. `reports` now has RLS enabled with **no** SELECT policy for `authenticated` — every technician reads zero rows — while `anon` keeps the grants from 002. The application looks empty and the hole stays open.

Prescription, grounded in the two orderings above being the only two available:

1. Add the migration that creates `public.user_tenant_access` and sequence it strictly before 003. Until it exists, 003 is not a fix, it is a failed deploy waiting to happen.
2. Apply migrations as a distinct step that gates the app deploy — app revision does not receive traffic until the ledger tail equals the migration directory tail at the deployed SHA. The current arrangement has no such step to gate; see below.
3. Make the disagreement fail the build, not a person's memory. `python3 ~/.claude/skills/engineering-requirements/scripts/migration_drift.py check --root <repo> --db-url "$DRIFT_DB_URL"` does exactly this comparison; exit 1 is drift, exit 2 is cannot-determine and must fail the pipeline rather than skip it.

## No down path exists for 003

[VERIFIED] `grep -rni "down\|rollback\|revert" .` over the whole fixture returns nothing. There is no down migration, no revert script, and no rollback note in `spec.md` — its Done-when list is "Deploy is repeatable and observable. / Migrations are applied and recorded. / Tests gate the classification engine." Reversal is not mentioned.

It is 3am and 003 has just gone in. Rolling back the application code does not undo it, because 003 is destructive in the policy layer: `003_rls_fix.sql:2` is `DROP POLICY IF EXISTS "Anon read access" ON public.reports;` and `003_rls_fix.sql:8` is `REVOKE ALL ON public.reports FROM anon;`. Neither is restored by deploying the previous image. The previous image expects a grant that is gone.

Re-running 002 is not the escape hatch either. `002_policies.sql:3` is a bare `CREATE POLICY "Anon read access"` with no `IF NOT EXISTS` and no `DROP` ahead of it, so re-applying it against a database where the policy still exists raises `42710 policy already exists` and against one where 003 partially ran it silently re-opens the cross-tenant read. [INFERENCE] on the error code — Postgres has no `CREATE POLICY IF NOT EXISTS`; I have watched exactly this turn a rollback into a second incident, where the operator's only working recovery was hand-written SQL typed into a console at 3am and never committed anywhere.

Prescription: ship `003_rls_fix.down.sql` alongside 003 that recreates the prior policy and grants explicitly, and rewrite the forward file so each statement is idempotent (`DROP POLICY IF EXISTS reports_tenant_select` before the `CREATE POLICY`). Write the exact recovery sequence into the change itself — the sequence someone runs at 3am should be a file in the repo, not a reconstruction from two migration files under pressure.

## Nothing observes whether the deploy took

There is no pipeline in this repository to observe with. [VERIFIED] `find . -iname "*.yml" -o -iname "*.yaml" -o -iname "package*.json" -o -iname "Dockerfile*" -o -iname ".env*" -o -iname "*.toml" | wc -l` returns `0`. The spec asks for "Deploy is repeatable and observable"; nothing in the tree makes either claim checkable.

The one endpoint that could carry the observation cannot. `app/api/health/route.ts:4`:

```
    version: process.env.NEXT_PUBLIC_APP_VERSION || "1.0.0",
```

Two defects in one line. The `|| "1.0.0"` fallback means an unset variable returns a plausible version rather than an error, so a health check that reads this field cannot distinguish "new revision serving" from "old revision serving" from "variable was never wired" — all three return `200 {"status":"ok","version":"1.0.0"}`. And `NEXT_PUBLIC_` is inlined at build time, so the value is fixed by whichever environment ran the build, not by the environment serving the request; a promoted-alias step that silently no-ops looks identical to a successful promotion. [INFERENCE] on the inlining mechanism — this is standard Next.js `NEXT_PUBLIC_` behaviour and it is precisely why a build-time constant is the wrong carrier for a deploy-time fact.

Nothing anywhere reports the migration state. The health payload has `status`, `version`, `timestamp` and no field derived from the database at all, so an operator watching this endpoint would have seen green throughout the entire window in which 003 sat unapplied.

I ran the drift check itself and it is worth reporting how it behaved here, because it is the tool an operator would reach for. [VERIFIED] `python3 scripts/migration_drift.py self-test` prints `SELF-TEST PASS` and exits 0, so the check can fail. Run against this repo with the ledger, `check --root harness/fixture --applied-from-file supabase/APPLIED_LEDGER.txt` exits 1 — correct — but reports:

```
  2 version(s) applied to the database with no file in the repository:
    001  (applied out of band ...)
    002  (applied out of band ...)
```

and says nothing about 003. The cause is `--ref` defaulting to `origin/main` (`scripts/migration_drift.py:238`) while these migration files are untracked — `git ls-files supabase/migrations` returns empty, so the repository side of the comparison is empty and the diagnosis inverts. The exit code is right for the wrong reason, and an operator following the message would go hunting two migrations that are fine while the unapplied security fix goes unmentioned.

Prescription:

1. Serve the deployed commit SHA from a runtime source, not a `NEXT_PUBLIC_` build constant, and remove the `|| "1.0.0"` default — an unknown version must be an error, not a number.
2. Add a field to the health payload read live from the ledger (`SELECT max(version) FROM supabase_migrations.schema_migrations`), so one GET against the live URL answers "is this change actually in effect".
3. Make the post-deploy gate a request to the live URL asserting both fields equal the values expected for the release, not the pipeline's own exit code.
4. When wiring the drift check into CI, pass the ref that actually contains the migrations (or `--ref ""` for the working tree) and assert non-zero once as a positive control — a drift check that has never failed against this repo is indistinguishable from one that cannot.
