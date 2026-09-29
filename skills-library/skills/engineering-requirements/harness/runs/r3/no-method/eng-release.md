by: eng-release
contributed: [eng-release]
categories:
  migration:     {state: PRESCRIBED, ref: "#migration-003-is-merged-but-never-applied-and-cannot-apply", by: eng-release, blocking: true}
  observability: {state: PRESCRIBED, ref: "#no-observation-proves-which-build-or-schema-is-live", by: eng-release, blocking: true}
  rollback:      {state: PRESCRIBED, ref: "#no-down-path-for-003", by: eng-release, blocking: true}
cross_domain:
  - "vitest.config.ts include globs match zero test files, so the suite exits green having run nothing — eng-test owns the oracle"
  - "003 depends on a public.user_tenant_access table no migration in this repo creates; who owns that table and its rows is eng-data's call"
  - "002's live policy grants anon SELECT USING (true) plus full DML on public.reports right now — eng-authz owns whether that policy shape was ever acceptable"

## Migration 003 is merged but never applied and cannot apply

The ledger and the migration directory disagree, and the disagreement is the security gate itself.

`[VERIFIED]` `supabase/APPLIED_LEDGER.txt:1-2` records only:

```
001
002
```

`[VERIFIED]` `supabase/migrations/003_rls_fix.sql:1` exists in the repository and is committed:

> `-- Tenant-scoped replacement for the permissive policy in 002.`

Drift check, run against `HEAD` with the ledger as the applied side, confirms it — and its own self-test passed first, so a null result here would have been meaningful:

```
MIGRATION DRIFT
  1 migration(s) in the repository are NOT applied to the database:
    003_rls_fix.sql, merged 2026-07-29
```

Concretely, the running database is at 002. That means the policy live in production right now is `[VERIFIED]` `supabase/migrations/002_policies.sql:3-4`:

> `CREATE POLICY "Anon read access" ON public.reports`
> `  FOR SELECT USING (true);`

and `[VERIFIED]` `supabase/migrations/002_policies.sql:6`:

> `GRANT SELECT, INSERT, UPDATE, DELETE ON public.reports TO anon, authenticated;`

So `spec.md:10` — "Tenants must not read each other's reports" — is satisfied in the repository and violated in the system. Anyone holding the anon key reads every tenant's reports and can also insert, update and delete them. A reviewer reading only the diff sees a tenant-scoped policy and concludes the gate holds.

Worse, applying 003 as written will fail. `[VERIFIED]` `supabase/migrations/003_rls_fix.sql:6`:

> `  USING (tenant_id IN (SELECT tenant_id FROM public.user_tenant_access WHERE user_id = auth.uid()));`

`grep -rn "user_tenant_access"` over the whole fixture returns exactly that one line — no migration creates the table. `[INFERENCE]` Postgres resolves relations in a policy expression at `CREATE POLICY` time, so this aborts with `relation "public.user_tenant_access" does not exist`. If the operator runs the migration inside a transaction, `DROP POLICY IF EXISTS "Anon read access"` on line 2 rolls back with it and the permissive policy survives; if they run the statements loose, the drop commits and the replacement does not, leaving `reports` with RLS enabled and **no** SELECT policy — every authenticated read returns zero rows and the product looks empty rather than broken. Both outcomes are silent. This is the ordering hazard in its sharpest form: the migration is not merely unapplied, it is unappliable, and nothing in the repo distinguishes those two states.

Prescription, grounded in the drift check being a merge gate rather than an afterthought:

1. Add the `user_tenant_access` table (and its own RLS) in a migration ordered **before** 003, or fold it into 003 above the policy. Do not add a fourth migration on top of a drifted ledger until 003 applies.
2. Wrap 003 in an explicit `BEGIN`/`COMMIT` so the partial-apply outcome cannot occur.
3. Gate merge on `migration_drift.py check --ref origin/main --db-url "$DRIFT_DB_URL"` exiting 0, and treat exit 2 as failure. Note this run needed `--ref HEAD`: against the default `origin/main` the check found zero repo migrations and reported the applied ones as out-of-band rather than reporting 003 missing. Whichever ref CI pins, prove the check fails on a seeded drift before trusting a pass.

## No observation proves which build or schema is live

There is nothing in this repository that could tell you the state above. `[VERIFIED]` — `find` across the fixture for `*.yml`, `*.yaml`, `package*.json`, `Dockerfile*`, `.env*` and `*.toml` returns nothing. No CI workflow, no deploy config, no lockfile, no environment file. So "Deploy is repeatable and observable" (`spec.md:13`) has no mechanism behind it at all, and every deploy claim rests on somebody's memory of running a command.

The one probe that exists actively obscures the answer. `[VERIFIED]` `app/api/health/route.ts:4`:

> `    version: process.env.NEXT_PUBLIC_APP_VERSION || "1.0.0",`

`grep -rn "APP_VERSION"` finds that line and nothing else — no build step, no env file, no CI job ever sets the variable, so the endpoint returns the literal string `1.0.0` on every revision that will ever ship. `[INFERENCE]` The `|| "1.0.0"` fallback is the specific mechanism: a container serving last month's build and a container serving today's return byte-identical bodies apart from `timestamp`, which moves regardless. A promoted-alias step that silently no-ops, a rollout that never shifted traffic, and a successful deploy are indistinguishable to any smoke test hitting this route. `status: "ok"` is a constant — it is not derived from any dependency, so the route also answers `ok` while the database is unreachable.

Nothing anywhere reports migration state, which is why the 003 drift can sit merged for as long as it likes without a single alert.

Prescription:

- Emit an immutable build identity — the commit SHA injected at build time, failing the build if absent rather than defaulting. A version endpoint that cannot say "unknown" cannot be trusted when it says a number.
- Add the applied migration head (`SELECT max(version) FROM supabase_migrations.schema_migrations`) to the same payload, so the post-deploy check compares live schema head against the SHA's expected head and alerts on mismatch. That single comparison is what turns finding one from invisible into a page.
- Make `status` reflect a real dependency check, or rename it so nobody builds an alert on a constant.
- Run the post-deploy assertion against the live URL after the deploy and fail the pipeline on mismatch. The pipeline's own exit code is evidence that a command returned zero, not that the system changed.

## No down path for 003

`[VERIFIED]` — `find` for any file matching `*down*`, `*revert*` or `*rollback*` across the fixture returns nothing. There are exactly three files in `supabase/migrations/` and all three are forward-only.

The 3am sequence, concretely. 003 finally applies. The mobile client or any integration still authenticating with the anon key starts returning empty result sets and permission errors, because `[VERIFIED]` `supabase/migrations/003_rls_fix.sql:8`:

> `REVOKE ALL ON public.reports FROM anon;`

The on-call engineer does the obvious thing and rolls the application back to the previous release. That release is the one that expected the 002 grants. The schema does not roll back with it, so the rollback changes nothing and the outage continues while everyone assumes it has been reverted — the worst shape of failure, because the recovery action produces no signal. Restoring service now requires hand-writing DDL against production under time pressure, and `DROP POLICY IF EXISTS` on line 2 has already destroyed the only record of what the previous policy was outside git history.

`[INFERENCE]` This is the standard mechanism where a schema change is safe to apply and unsafe to leave, and the reversal was never written because the forward path was the only one exercised.

Prescription:

- Write `003_rls_fix.down.sql` that recreates the prior policy and grants verbatim, and rehearse it against a restored snapshot before 003 goes near production. An untested down migration is a rollback plan in the same sense that an untested backup is a backup.
- Decide explicitly whether any anon-key caller still exists before applying 003. If one does, this needs an expand-then-contract shape — add the tenant-scoped policy, migrate callers to authenticated, then revoke anon in a separate later migration — so the revoke is never the same deploy as the cutover.
- Record the rollback sequence as an ordered pair (code revision, schema version). "Roll back the code" is not a rollback plan for a change that alters the schema.
