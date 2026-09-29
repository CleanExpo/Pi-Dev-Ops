by: eng-release
contributed: [eng-release]
categories:
  migration:     {state: PRESCRIBED, ref: "#migration-003-is-merged-but-not-applied", by: eng-release, blocking: true}
  observability: {state: PRESCRIBED, ref: "#no-post-deploy-observation-proves-this-is-in-effect", by: eng-release, blocking: true}
  rollback:      {state: PRESCRIBED, ref: "#no-down-path-for-003", by: eng-release, blocking: true}
cross_domain:
  - "vitest.config.ts:4-5 includes only `lib/**/__tests__/**` and `app/**/__tests__/**`, but the only test file is `__tests__/engine.test.ts` at the repo root — the suite that gates the classification engine collects it under neither glob; eng-test owns what that means for the oracle"
  - "003 references `public.user_tenant_access` as the tenancy source of truth and no migration in this repo creates it — eng-data owns where that table comes from, eng-authz owns whether the predicate is the right one"
  - "002_policies.sql:6 grants anon INSERT, UPDATE and DELETE (not just SELECT) on reports — eng-authz owns whether a write grant to anon was ever intended"
  - "the repo has no package.json, no lockfile, no CI workflow and no deploy config of any kind, so there is no pipeline to review — eng-supply-chain owns the install/build side of that absence"

## Migration 003 is merged but not applied

`supabase/APPLIED_LEDGER.txt` records exactly two versions — `001` (line 1) and `002` (line 2). `supabase/migrations/003_rls_fix.sql` exists on disk and is in no ledger line. **[VERIFIED]** The repo's own drift check confirms it, and its positive control passes first, so this is a real failure and not a broken check:

```
$ python3 .../migration_drift.py self-test
SELF-TEST PASS: the check reports drift, tolerates timestamp-length conventions, reports out-of-band versions, and fails closed without a database.
$ python3 .../migration_drift.py check --root . --ref HEAD --applied-from-file supabase/APPLIED_LEDGER.txt
MIGRATION DRIFT
  1 migration(s) in the repository are NOT applied to the database:
    003_rls_fix.sql, merged 2026-07-29
EXIT=1
```

Spec §2 states the gate this file is supposed to satisfy:

> - Tenants must not read each other's reports.

and §3 states it as already done:

> - Migrations are applied and recorded.

Neither is true. What is actually live is 002, whose policy is unconditional — `supabase/migrations/002_policies.sql:3-4`: **[VERIFIED]**

> `CREATE POLICY "Anon read access" ON public.reports`
> `  FOR SELECT USING (true);`

and `002_policies.sql:6`: **[VERIFIED]**

> `GRANT SELECT, INSERT, UPDATE, DELETE ON public.reports TO anon, authenticated;`

The concrete scenario, today, with no attacker sophistication: anyone holding the publishable anon key — which ships in the client bundle — issues `select * from public.reports` and receives every tenant's rows, and `delete from public.reports` and removes them, because the REVOKE that closes both is sitting unapplied in a file. The tenancy gate reads as satisfied in review because the fix was *merged*; merged and applied are two separate facts and only one of them happened.

**Second, and worse: 003 cannot apply as written.** `003_rls_fix.sql:6` predicates on a table that no migration in this repo creates — `grep -rn "CREATE TABLE" supabase/migrations` returns only `001_init.sql:1` for `public.reports`: **[VERIFIED]**

> `  USING (tenant_id IN (SELECT tenant_id FROM public.user_tenant_access WHERE user_id = auth.uid()));`

Postgres resolves that relation at `CREATE POLICY` time, so statement 2 of the file raises `relation "public.user_tenant_access" does not exist`. **[INFERENCE]** — the mechanism is ordinary name resolution in DDL; I have not run it, and `psql -c "\d public.user_tenant_access"` against the target database settles it. The release consequence depends entirely on something nobody has decided: whether the runner wraps the file in a transaction. If it does, the whole file aborts and you stay in the leaking 002 state. If it does not — statement-per-statement is the common default for ad-hoc `psql -f` and for several migration tools — then statement 1 succeeds, statement 2 fails, statement 3 never runs, and you land in a state that exists in nobody's plan: RLS enabled, the permissive SELECT policy dropped, **no** SELECT policy for `authenticated`, and anon still holding full DML from 002. Every legitimate authenticated read returns zero rows while the anon write grant survives. That is strictly worse than either endpoint, and it is reachable by one apply attempt.

**Third, the ledger cannot detect an edited migration.** `APPLIED_LEDGER.txt` stores bare version numbers and nothing else — no checksum, no hash, no applied-at. **[VERIFIED]** (the whole file is two lines, `001` and `002`). Anyone can edit `001_init.sql` or `002_policies.sql` after they ran and the ledger still reads "applied"; the deployed schema and the file diverge permanently and silently. It is also a hand-maintained text file, not a table the database writes, so the word "recorded" in spec §3 records only that a human typed a number.

**Prescription** (grounded in the drift-check contract this repo already ships, not invented):
1. Do not apply 003 as written. Land `user_tenant_access` in its own migration first, ordered before it, or rewrite 003's predicate against a column that exists.
2. Wrap each migration file in an explicit `BEGIN; … COMMIT;` so a mid-file failure cannot leave the partial state above. Assert this rather than assuming the runner's default.
3. Replace `APPLIED_LEDGER.txt` with the database's own ledger (`supabase_migrations.schema_migrations`) as the authority, and record a content hash per version, so an edited-after-apply file is detectable.
4. Run `migration_drift.py check` in the pipeline with a real `--db-url` and fail the deploy on exit 1 **and** exit 2. Exit 2 means "cannot determine", and a check that cannot determine is a check that has stopped protecting you.

## No post-deploy observation proves this is in effect

Spec §3 lists this as done:

> - Deploy is repeatable and observable.

The only observation surface in the repo is `app/api/health/route.ts`, and it cannot distinguish a successful deploy from no deploy at all. Line 4: **[VERIFIED]**

> `    version: process.env.NEXT_PUBLIC_APP_VERSION || "1.0.0",`

Three separate ways that returns a comforting answer while nothing shipped. The `|| "1.0.0"` fallback means an unset variable and a genuine 1.0.0 deploy are byte-identical responses — the single observation you would reach for to confirm the new revision is receiving traffic answers "yes" when the promote step silently no-opped. The value is a literal string, not a build SHA, so two different builds of the same version number are indistinguishable. And the `NEXT_PUBLIC_` prefix means it is inlined into the bundle at build time, so it reports the environment the build ran in, not the environment the running process is in. **[INFERENCE]** on the inlining — the mechanism is Next.js's build-time substitution of `NEXT_PUBLIC_*`; `grep -r NEXT_PUBLIC_APP_VERSION` across the deploy config would confirm where it is set, and no such config exists in this repo to grep.

Nothing in the endpoint touches the database. `/api/health` returns `{"status":"ok"}` with a schema that is a migration behind and a tenant-isolation hole open — which is exactly the state the repo is in right now, and exactly why the drift above survived to review. The pipeline's own exit code is the only signal, and the pipeline's exit code is a statement about the pipeline.

**Prescription:** the health payload must be an observation of the running system, not of the build's environment. Report the deployed commit SHA with no fallback default — absent means absent, and the check fails rather than returning a plausible string. Report the max applied version read live from the migration ledger table on each call. Then have the deploy job, after promoting, fetch the live URL and assert both against the SHA it just deployed and the migration set it just applied. That single observation is the one thing that separates "the pipeline said success" from "the new code is serving traffic against the new schema", and right now nothing in this repo makes it.

## No down path for 003

`003_rls_fix.sql` is eight lines and every statement is forward-only. **[VERIFIED]** — the file's two destructive statements are line 2:

> `DROP POLICY IF EXISTS "Anon read access" ON public.reports;`

and line 8:

> `REVOKE ALL ON public.reports FROM anon;`

There is no paired down file: `find . -name "*down*"` over the whole fixture returns nothing. **[VERIFIED]**

So the 3am sequence does not exist, and the obvious substitutes are both wrong. Rolling back the *application* to a pre-003 revision does not undo 003 — the grants stay revoked and the dropped policy stays dropped, so old code now points at a schema that can no longer serve it. Re-running 002 to restore the old state re-executes line 6 of that file and re-grants anon `SELECT, INSERT, UPDATE, DELETE` — the reversal of a tenant-isolation fix is a full re-opening of the hole, not a partial one, and whoever runs it at 3am under pressure will not notice they just restored the anon write grant along with the read.

The trigger is concrete. `lib/sync-queue.ts:33-37` drains offline entries with only a content-type header and no credential visible in this repo: **[VERIFIED]**

> `        headers: { "content-type": "application/json" },`

If the path behind `entry.endpoint` reaches Postgres with the anon key, every queued technician capture starts failing the moment line 8's REVOKE lands, entries accumulate retryCount to `MAX_RETRY_COUNT` and are marked failed, and no code rollback restores them. **[INFERENCE]** — which credential that endpoint uses is not determinable from this repo; reading the server-side client construction, or `grep -rn "SUPABASE.*KEY"` in the real application, decides whether this fires.

**Prescription:** before 003 is applied, write its down file explicitly and separately from 002 — drop `reports_tenant_select`, restore only the grants the application genuinely needs, and never by re-running 002. Then rehearse the down path against a scratch database and record the exact command sequence next to the migration, because a rollback plan that has never been executed is a hypothesis. If the decision is that 003 is deliberately one-way, say so in the file and delete "roll back the code" from the incident options, so nobody reaches for it under pressure and makes things worse.
