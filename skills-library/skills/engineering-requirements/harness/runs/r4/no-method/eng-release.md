by: eng-release
contributed: [eng-release]
categories:
  migration:     {state: PRESCRIBED, ref: "#migration-003-is-merged-but-not-applied", by: eng-release, blocking: true}
  failure_modes: {state: PRESCRIBED, ref: "#migration-003-cannot-apply-as-written", by: eng-release, blocking: true}
  observability: {state: PRESCRIBED, ref: "#nothing-observes-the-live-system-after-deploy", by: eng-release, blocking: true}
cross_domain:
  - "003 has no down path — DROP POLICY and REVOKE ALL are not reversible from any file in the repo; eng-rollback owns the 3am sequence"
  - "public.user_tenant_access is referenced by a policy but created by no migration and modelled nowhere in lib/schema.prisma — eng-data owns whose table it is"
  - "while 003 is unapplied the live predicate is USING (true) with GRANT SELECT to anon on public.reports — eng-authz owns whether the replacement predicate is correct, but the exposure is live now, not hypothetical"
  - "vitest.config.ts includes only lib/**/__tests__/** and app/**/__tests__/**, while the only test file is __tests__/engine.test.ts at the repo root, so the suite matches zero files and exits green — eng-test owns the oracle"

## Migration 003 is merged but not applied

The ledger and the migration directory disagree, which is this seat's unconditional dispatch trigger. I ran the drift check with a positive control first, because a check that has never failed is indistinguishable from one that cannot fail.

Positive control, `migration_drift.py self-test`, exit 0:

> `SELF-TEST PASS: the check reports drift, tolerates timestamp-length conventions, reports out-of-band versions, and fails closed without a database.`

Then against the fixture, `check --root . --ref worktree --applied-from-file supabase/APPLIED_LEDGER.txt`, exit 1:

> `1 migration(s) in the repository are NOT applied to the database:` / `003_rls_fix.sql`

[VERIFIED] `supabase/APPLIED_LEDGER.txt:1-2` — the entire file is `001` and `002`. [VERIFIED] `supabase/migrations/003_rls_fix.sql:1` — `-- Tenant-scoped replacement for the permissive policy in 002.`

The concrete state this leaves in production: `002_policies.sql:3-4` is what is actually running —

> `CREATE POLICY "Anon read access" ON public.reports`
>   `FOR SELECT USING (true);`

— together with `002_policies.sql:6`, `GRANT SELECT, INSERT, UPDATE, DELETE ON public.reports TO anon, authenticated;`. Spec gate 2.3 says "Tenants must not read each other's reports." The migration that satisfies that gate exists in the repo, reviews as correct, and has never run. Every day the spec looks satisfied and the database is not.

**Prescription.** Before any further migration is authored: apply 003, then make the ledger a derived artifact rather than a hand-maintained one. `APPLIED_LEDGER.txt` is checked in and nothing reads it — [VERIFIED] `grep -rn "APPLIED_LEDGER"` across the fixture returns no hits outside the file itself. A ledger only a human edits records intent, not fact. It must be written by whatever applies the migration, or replaced by a query against `supabase_migrations.schema_migrations`. Add the drift check to CI on exit codes 1 **and** 2; exit 2 is a finding, because a check that cannot reach the database and reports "skipped" is the fail-open it was built to catch.

## Migration 003 cannot apply as written

This is not "003 has not been applied yet" — 003 cannot succeed, which is the likeliest reason the ledger stopped at 002 and why "apply the missing migration" is not a one-line fix.

[VERIFIED] `supabase/migrations/003_rls_fix.sql:6` —

> `USING (tenant_id IN (SELECT tenant_id FROM public.user_tenant_access WHERE user_id = auth.uid()));`

[VERIFIED] the only `CREATE TABLE` in the repository is `supabase/migrations/001_init.sql:1`, `CREATE TABLE public.reports (`. `grep -rn "user_tenant_access"` returns exactly one hit, the reference above. [INFERENCE] Postgres resolves relation names in a policy expression at `CREATE POLICY` time, not at first evaluation, so this statement raises `42P01 relation "public.user_tenant_access" does not exist` and the migration aborts. I have watched this exact shape sit unapplied for months because the failure is logged once by whoever ran it and never surfaces again.

The ordering inside the file is what makes the failure dangerous rather than merely annoying. `003_rls_fix.sql:2` is `DROP POLICY IF EXISTS "Anon read access" ON public.reports;` and it runs **before** the `CREATE POLICY` that fails. If the applier wraps each file in a transaction the drop rolls back and you are left in today's permissive state; if it does not — and nothing in this repository states which, because there is no `supabase/config.toml`, no CI workflow, no `package.json` and no `Dockerfile` ([VERIFIED] a `find` for `*.yml`, `*.yaml`, `*.toml`, `Dockerfile*`, `package.json`, `*.lock`, `*.env*`, `*.json` under the fixture returned nothing) — the drop lands, the create fails, and `public.reports` is left RLS-enabled with no SELECT policy at all. Deny-by-default: every authenticated read returns zero rows, reports silently vanish from every tenant's view, and no error is raised anywhere in the application. That is a full outage that looks like an empty database.

**Prescription.** Three things, in order. Create `public.user_tenant_access` (with its own RLS) in a migration that precedes 003 rather than assuming it exists. State explicitly that each migration runs in a single transaction, and prove it by asserting a failed migration leaves the policy set unchanged. Do not reorder to put the `CREATE` before the `DROP` as a workaround — that fixes this instance and leaves the general half-applied hazard in place.

## Nothing observes the live system after deploy

Spec gate 3.1 is "Deploy is repeatable and observable." The only endpoint that could carry that observation cannot.

[VERIFIED] `app/api/health/route.ts:4` —

> `version: process.env.NEXT_PUBLIC_APP_VERSION || "1.0.0",`

Two mechanisms defeat this. First, [VERIFIED] `grep -rn "NEXT_PUBLIC_APP_VERSION\|BUILD_SHA\|VERCEL_GIT"` across the fixture returns this single line — nothing sets the variable, and there is no `.env` or CI file to set it in. [INFERENCE] `NEXT_PUBLIC_*` is inlined into the bundle at build time in Next.js, so an unset variable is not "empty at runtime, fix the env later"; the literal `"1.0.0"` is compiled in and every deploy, forever, reports the same version. Second, the payload reports nothing about schema state, so a container running new code against a database still at 002 returns byte-identical output to one running against 003.

The observation that would prove this deploy is in effect therefore does not exist, and a deploy that silently no-ops — a promoted alias that did not move, a rollback that skipped — is indistinguishable from success. That is precisely how 003 has stayed unapplied without anyone noticing.

**Prescription.** Make `/api/health` answer both halves of "which build, which schema": a build identifier read at runtime from a non-`NEXT_PUBLIC_` server variable (the commit SHA the pipeline injects), and the greatest applied migration version read from `supabase_migrations.schema_migrations`. Remove the `|| "1.0.0"` fallback — an unset version must fail the health check loudly, not answer plausibly. Then add a post-deploy step that fetches the live URL and asserts the returned SHA equals the SHA just deployed, and fails the pipeline when it does not. The pipeline's own exit code is not evidence the running system changed.
