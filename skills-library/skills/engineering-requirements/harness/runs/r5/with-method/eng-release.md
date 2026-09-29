by: eng-release
contributed: [eng-release]
categories:
  migration:     {state: PRESCRIBED, ref: "#migration-003-is-merged-but-not-applied", by: eng-release, blocking: true}
  rollback:      {state: PRESCRIBED, ref: "#no-down-path-for-003",                    by: eng-release, blocking: true}
  observability: {state: PRESCRIBED, ref: "#nothing-observes-the-deployed-system",     by: eng-release, blocking: true}
cross_domain:
  - "the live policy right now is `FOR SELECT USING (true)` with DELETE granted to `anon` — eng-authz owns whether that predicate and grant set are correct once 003 does land"
  - "`vitest.config.ts` includes `lib/**/__tests__/**` and `app/**/__tests__/**`, but the only test file is at repo root `__tests__/engine.test.ts`, so zero tests match — eng-test owns the oracle"
  - "`lib/schema.prisma` models User/Inspection/AuditLog while `supabase/migrations` models `public.reports`; two disjoint schema sources of truth — eng-data owns which is authoritative"
  - "`lib/notify.ts` swallows every non-2xx and every throw into `console.error` and resolves void — eng-failure owns whether a dropped insurer notification may fail silently"

## Migration 003 is merged but not applied

The repository's migration directory and its applied ledger disagree, and the disagreement is exactly the security fix.

`[VERIFIED]` `supabase/APPLIED_LEDGER.txt:2` — the ledger's last line is:

> `002`

`[VERIFIED]` `supabase/migrations/003_rls_fix.sql:1` exists on disk:

> `-- Tenant-scoped replacement for the permissive policy in 002.`

I ran the bench's drift check, positive control first. `self-test` returned exit 0 with `SELF-TEST PASS: the check reports drift, tolerates timestamp-length conventions, reports out-of-band versions, and fails closed without a database.` — so the check is capable of returning a non-null result. Then `migration_drift.py check --root . --ref "" --applied-from-file supabase/APPLIED_LEDGER.txt` returned exit 1: `1 migration(s) in the repository are NOT applied to the database: 003_rls_fix.sql`.

The concrete state this produces: the database is running `002`, so `[VERIFIED]` `supabase/migrations/002_policies.sql:4` is the live SELECT predicate —

> `  FOR SELECT USING (true);`

— and `[VERIFIED]` `supabase/migrations/002_policies.sql:6` is the live grant:

> `GRANT SELECT, INSERT, UPDATE, DELETE ON public.reports TO anon, authenticated;`

Any authenticated technician reads every tenant's reports, and an anonymous key can delete them. The spec gate `[VERIFIED]` `spec.md:11` —

> `- Tenants must not read each other's reports.`

— is false in the running system while the fix sits merged in `main`. A reviewer reading the diff sees the gate satisfied. This is the gap between "merged" and "applied" that the ledger is the only witness to, and nothing reads the ledger.

**Applying it is not a one-liner, which is probably why it stalled.** `[VERIFIED]` `supabase/migrations/003_rls_fix.sql:6`:

> `  USING (tenant_id IN (SELECT tenant_id FROM public.user_tenant_access WHERE user_id = auth.uid()));`

`grep -rn "user_tenant_access" .` returns exactly that one line. No migration in this repo creates `public.user_tenant_access`. `[INFERENCE]` Postgres resolves the policy expression at `CREATE POLICY` time, so against a database built from `001` and `002` this migration aborts with `relation "public.user_tenant_access" does not exist`. If it *does* apply in production, the table was created out of band and the schema is already drifted in the other direction — a change in the database with no file. Both branches are bad and they are distinguishable only by looking.

Second silent decision: there are two migration systems here — `supabase/migrations/*.sql` and `lib/schema.prisma`, which carries its own Prisma migrate lineage. Nothing in the repo states which one runs at deploy, in what order relative to the app rollout, or whether one is dead. Method §4: a half-finished migration is worse than either end state, because the system has two truths and no rule for which wins.

**Prescribed:**

1. Do not add a migration on top of a drifted ledger. Resolve `003` first: add the migration that creates `public.user_tenant_access` (with its own tenancy grants) as `003`, renumber the RLS fix to `004`, and apply them as one transaction.
2. Make the drift check a required CI job on every PR, not a thing a reviewer remembers to run — method §6, when a review comment recurs, replace it with a rule. `migration_drift.py check --root . --db-url "$DRIFT_DB_URL"`, treating its exit 2 (cannot determine) as a failure, not a skip. A check that cannot reach the ledger and passes is the same as no check.
3. State the applied ordering explicitly in the deploy config: migrations apply *before* the new revision takes traffic, and the pipeline must fail if the migration step is skipped rather than proceeding to the app deploy. Right now the ordering is only correct in whatever direction the pipeline happens to run.
4. Declare one schema authority. If Prisma is vestigial, delete `lib/schema.prisma`; if it is live, say which tables each system owns.

*Grounding:* the drift is a tool result from this session, not a reading of the diff. What would overturn this: a production ledger query showing `003` applied, i.e. `select version from supabase_migrations.schema_migrations order by version;` returning a `003` row — in which case `APPLIED_LEDGER.txt` is itself the stale artifact and the finding becomes "the repo's own ledger lies", which is the same class of problem.

**Blocking.** A security fix that exists only as a merged file is not a fix.

## No down path for 003

`003` is one-way as written. `[VERIFIED]` `supabase/migrations/003_rls_fix.sql:2`:

> `DROP POLICY IF EXISTS "Anon read access" ON public.reports;`

and `[VERIFIED]` `supabase/migrations/003_rls_fix.sql:7`:

> `REVOKE ALL ON public.reports FROM anon;`

There is no `003_rls_fix.down.sql` and no `-- rollback` block; `ls supabase/migrations/` returns three files, all forward.

The 3am scenario is specific. `003` applies. The tenant-scoped predicate turns out to be wrong for some population — a technician whose `user_tenant_access` row was never backfilled, say — and reports start returning empty for real users. The instinct is "roll back the code". That does nothing: the code did not change the policy, the migration did. The previous release expected `anon` to hold `SELECT`, and that grant is now revoked, so rolling back the deployment lands the old build on a schema it can no longer read. The database is now the only thing that can be reverted, and reverting it means re-granting `anon` full DML on `public.reports` — restoring the vulnerability under time pressure, by hand, with no reviewed script.

**Prescribed:**

1. Ship the down migration in the same commit as the up. For `003` it is a reviewed, checked-in script that recreates the prior policy and grants — written now, in daylight, not typed into `psql` at 3am.
2. Prefer a reversible shape over a reversal script where one exists: add the tenant-scoped policy *first*, run both policies concurrently, verify the new one returns the same rows for known-good users, and drop the permissive one in a separate later migration. That makes the risky step a `DROP` you can defer rather than a `REVOKE` you must undo.
3. Write down the rollback decision rule: which observation triggers it, who may pull it, and the exact command sequence. `rollback` is not answered by "revert the PR" when a migration is in the change.
4. Because `REVOKE`/`DROP POLICY` cannot be undone by a code rollback, the deploy must not be considered complete until the post-deploy observation below passes — otherwise the irreversible step lands before anyone can see whether it should have.

*Grounding:* `[INFERENCE]` on the failure mechanism — I have watched a code rollback land on a tightened schema and fail closed on every request, which reads in the dashboard as a total outage rather than a rollback. What would overturn it: a rollback runbook elsewhere in the repo that covers schema reversal. `find . -type f` over the fixture returns no runbook, no CI config, no deploy config at all.

**Blocking.** An irreversible migration with no rehearsed down path is a decision to accept an unbounded outage, and nobody made it deliberately.

## Nothing observes the deployed system

The spec asks for this outright. `[VERIFIED]` `spec.md:13`:

> `- Deploy is repeatable and observable.`

Nothing implements the second half. The only endpoint in the repo is `app/api/health/route.ts`, and it cannot distinguish any of the states that matter.

`[VERIFIED]` `app/api/health/route.ts:3`:

> `    status: "ok",`

That is a constant. It is not derived from a database round-trip, a migration check, or anything else. It returns `ok` when the database is unreachable, when the schema is two migrations behind, and when the permissive policy is live.

`[VERIFIED]` `app/api/health/route.ts:4`:

> `    version: process.env.NEXT_PUBLIC_APP_VERSION || "1.0.0",`

The fallback is the defect. When the variable is unset — which is the normal state, since no `.env.example` or deploy config in this repo sets it — the endpoint reports a plausible-looking `1.0.0` forever. A container still serving last week's build and one serving today's return byte-identical bodies apart from `timestamp`, which is `new Date().toISOString()` and therefore always fresh. So the one field that could prove which build is receiving traffic proves nothing, and a promoted-alias step that silently no-ops looks exactly like a successful deploy. This is precisely how `003` reached `main` and stopped: the pipeline's exit code was the only thing anyone observed.

Second, and this is the environment-parity half: the alert path disappears when an environment variable is absent, silently. `[VERIFIED]` `lib/notify.ts:25`:

> `  const to = process.env.ALERT_EMAIL?.trim();`

and `[VERIFIED]` `lib/notify.ts:26`:

> `  if (to) {`

With `ALERT_EMAIL` unset, `runWatchdog` skips the send and returns `{healthy, alerted: false}` with no warning. `[VERIFIED]` `lib/notify.ts:7` shows the same pattern one level down — a missing `RESEND_API_KEY` logs `dropping mail` and returns. So on any environment where those two variables were not copied — a new staging project, a rebuilt prod, a preview deploy — the watchdog runs, finds problems, alerts nobody, and reports success to its caller. Nothing tests that the alerting path can actually deliver.

**Prescribed:**

1. Remove the `|| "1.0.0"` fallback. The build SHA is injected at build time and the endpoint returns 503 if it is missing — an unknown version is an unhealthy deploy, not a default one.
2. Add the applied schema version to the same payload, read live from the ledger (`select max(version) from supabase_migrations.schema_migrations`). This is the single observation my seat exists to ask for: one GET against the live URL that returns both which code and which schema are actually serving traffic.
3. Make the pipeline take that observation. After deploy, poll `/api/health` against the *public* URL, assert `version` equals the SHA just built and `schema` equals the highest file in `supabase/migrations`, and fail the deploy otherwise. The pipeline's own exit code is not evidence that the deploy happened.
4. Fail the deploy on missing `ALERT_EMAIL` or `RESEND_API_KEY` rather than degrading, and assert environment parity from a checked-in manifest of required variables — the current state is that parity is assumed and never verified.
5. Alert on the drift check itself running against production on a schedule, not only in CI. CI proves the repo is consistent with the ledger at merge time; only a scheduled check catches a migration that failed to apply after merge.

*Grounding:* `[VERIFIED]` on every code claim above. `[INFERENCE]` on the causal link between the absent post-deploy observation and `003` stalling unnoticed — the mechanism is the one in method §10: nobody asked what would prove the change is in effect, so nothing does. What would overturn it: an external monitor or deploy job outside this repo already performing that assertion. `[UNCONFIRMED]` — I cannot see beyond the fixture; `find . -type f` returns no CI, deploy, or monitoring configuration of any kind.

**Blocking.** This is the check whose absence let the other two findings survive to review.
