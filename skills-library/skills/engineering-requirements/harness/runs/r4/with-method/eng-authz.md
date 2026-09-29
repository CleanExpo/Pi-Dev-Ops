by: eng-authz
contributed: [eng-authz]
categories:
  invariants:    {state: PRESCRIBED, ref: "#the-tenant-invariant-is-stated-and-nothing-enforces-it", by: eng-authz, blocking: true}
  failure_modes: {state: PRESCRIBED, ref: "#production-is-running-the-permissive-policy-not-the-fix", by: eng-authz, blocking: true}
  migration:     {state: PRESCRIBED, ref: "#003-cannot-apply-as-written-and-breaks-writes-if-forced", by: eng-authz, blocking: true}
cross_domain:
  - "`vitest.config.ts` include globs never match `__tests__/engine.test.ts` at the repo root, so the suite that is supposed to gate the classification engine runs zero tests — eng-test owns that"
  - "`AuditLog` and `User` carry no tenant column while `Inspection` does, so a cascade or a join can surface rows across tenants at the ORM layer — eng-data owns the model"
  - "the spec's 'verification checklist complete before distribution' gate has no implementation, no column and no call site anywhere in the repo — eng-contract owns where that check lives"
  - "003 is authored but absent from `APPLIED_LEDGER.txt`, which is a ledger-drift signal beyond this one policy — eng-release owns the drift check"
  - "there is no down path for 002→003: re-granting `anon` after a failed rollout re-opens the read — eng-rollback owns the sequence"

## The tenant invariant is stated and nothing enforces it

The spec states the invariant plainly:

> - Tenants must not read each other's reports.

That sentence is the goal, not an enforceable assertion, and nothing in the repo turns it into one. Three separate gaps, each of which alone voids it:

**Nobody has said which role the request executes as.** There is no database client, connection string, or Supabase client construction anywhere in the repo — `grep -rniE "supabase|service_role"` over the tree returns only the three migration files and no application code. `[VERIFIED]` The policies in `003_rls_fix.sql` are written against `auth.uid()`:

> `USING (tenant_id IN (SELECT tenant_id FROM public.user_tenant_access WHERE user_id = auth.uid()));` — `supabase/migrations/003_rls_fix.sql:6` `[VERIFIED]`

`auth.uid()` returns null under a service-role key, and Supabase's `service_role` carries `BYPASSRLS`, so under that key the predicate is never evaluated at all. A Next.js server route reaching Postgres with the service key — the default shape for this stack — makes every policy in this repo decorative. This is the question that decides the invariant and the repo does not answer it. `[INFERENCE]` — I have watched exactly this land twice: policies reviewed, merged, correct, and enforcing nothing because the only caller held the bypass key.

**`FORCE ROW LEVEL SECURITY` is never set.** `[VERIFIED]` — `grep -riE "FORCE ROW"` over the tree returns no match; `supabase/migrations/002_policies.sql:1` is the only RLS statement and reads:

> `ALTER TABLE public.reports ENABLE ROW LEVEL SECURITY;`

`ENABLE` alone leaves the table owner exempt. Migrations run as owner, and anything that later connects as owner — a backfill, a report-generation job, a Prisma client pointed at the same database, since `lib/schema.prisma:10` declares `tenantId  String` with no policy behind it `[VERIFIED]` — reads every tenant's rows with the policies silently skipped.

**The predicate's own table does not exist.** `public.user_tenant_access` is referenced at `003_rls_fix.sql:6` and created by no migration. `[VERIFIED]` — it appears exactly once in the repo, in that USING clause. An invariant whose membership source is undefined has no meaning to test.

Prescribed, and deliberately the boring version — the method's first position says the burden of proof is on the clever thing, and my instinct here was to prescribe a policy suite with a helper function and a claims-based fast path; the method won, so this is the smallest set that can be asserted:

1. Name the runtime role in the spec, in one sentence, and add `ALTER TABLE public.reports FORCE ROW LEVEL SECURITY;`. If any path must use `service_role`, that path is named explicitly and re-derives `tenant_id` server-side; it is never taken because it was convenient.
2. Create `public.user_tenant_access` (`user_id`, `tenant_id`, PK on both) in a migration ordered *before* the policy that references it.
3. State the invariant as three testable assertions: (a) a session for tenant A selecting from `reports` returns zero rows written by tenant B; (b) a session for tenant A inserting a row with `tenant_id = B` is rejected by the database, not by the handler; (c) the same two assertions hold for whatever role the application actually connects as, not only for `authenticated`.
4. Per the method's sixth position — when a review comment recurs, replace it with a rule — the durable fix is not this policy but a check: a CI query asserting `relrowsecurity AND relforcerowsecurity` and at least one policy per command for every table carrying a `tenant_id` column. Without it this finding returns on the next table.

I would drop all of the above if the repo shows the request executes as `authenticated` through PostgREST with no owner-role path — that single observation overturns the first gap, though not the second or third. `[UNCONFIRMED]` The command that settles it: `SELECT current_user, rolbypassrls FROM pg_roles WHERE rolname = current_user;` run over the application's own connection string, plus `SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'reports';`.

## Production is running the permissive policy, not the fix

This is not a future risk; it is the current state. The ledger records what has been applied:

> `001` / `002` — `supabase/APPLIED_LEDGER.txt:1-2` `[VERIFIED]`

`003_rls_fix.sql` is authored and not applied. So the policy live on `public.reports` right now is the one 003 was written to remove:

> `CREATE POLICY "Anon read access" ON public.reports` / `  FOR SELECT USING (true);` — `supabase/migrations/002_policies.sql:3-4` `[VERIFIED]`

together with:

> `GRANT SELECT, INSERT, UPDATE, DELETE ON public.reports TO anon, authenticated;` — `supabase/migrations/002_policies.sql:6` `[VERIFIED]`

The concrete scenario, with inputs and state: a holder of the project's anonymous key — which by design ships to every browser — issues `select * from reports`. `USING (true)` admits every row, the `anon` grant admits the role, and `REVOKE ALL ON public.reports FROM anon` at `003_rls_fix.sql:8` `[VERIFIED]` has not run. Every report for every tenant is returned in one request, with no authentication and no rate limit in front of it. The spec's third gate is not merely unenforced; the shipped configuration is its exact inverse.

Blast radius and detection: total across tenants, unbounded in rows, and invisible. There is no logging of report reads anywhere in the repo, and `app/api/health/route.ts` reports only `status`, `version` and `timestamp` `[VERIFIED]` — nothing in this system can distinguish a legitimate read from a full-table exfiltration, so the first notification is an insurer or a customer. Reports distributed to insurers are third-party claim data, which is what makes this a notification-duty question as well as an availability one.

Prescribed:

- Treat this as a live exposure, not a pending migration. Before any further work: revoke the `anon` grant and drop `Anon read access` in production, accepting that reads break, rather than leaving `USING (true)` in place while the correct policy is finished.
- The reason this shipped is structural, not a mistake anyone will avoid by trying harder: nothing connects "policy merged" to "policy enforced". Add a post-deploy assertion that fails the deploy when any policy on a tenant-scoped table has `qual = 'true'`, or when a table with a `tenant_id` column grants anything to `anon`. `[UNCONFIRMED]` — `SELECT tablename, policyname, roles, cmd, qual FROM pg_policies WHERE schemaname = 'public';` against production is the query that both proves the current state and becomes the assertion.

## 003 cannot apply as written, and breaks writes if forced

Applying 003 is currently the obvious remediation, and it will not work. Two independent defects:

**It errors on execution.** `CREATE POLICY ... USING (... FROM public.user_tenant_access ...)` at `003_rls_fix.sql:6` `[VERIFIED]` parses the predicate at creation time, and `public.user_tenant_access` is created by no migration in the repo. The statement raises `relation "public.user_tenant_access" does not exist` and the migration aborts. If it aborts *after* `DROP POLICY IF EXISTS "Anon read access"` at `003_rls_fix.sql:2` `[VERIFIED]` and the runner does not wrap the file in a transaction, the table is left with RLS enabled and zero policies — reads return empty for everyone and the report pipeline stops. `[INFERENCE]` Which of the two outcomes you get depends entirely on whether the migration runner wraps each file in a transaction, and nothing in the repo states that it does.

**Once applied, it silently breaks capture.** 003 creates a `SELECT` policy only. RLS with no policy for a command denies that command, and the `INSERT, UPDATE, DELETE` grants to `authenticated` from `002_policies.sql:6` survive — 003 revokes from `anon` alone `[VERIFIED]`. So after 003 lands, an authenticated technician can read their tenant's reports and cannot write one: every insert fails with a policy violation, offline queue entries return non-2xx, `incrementRetry` at `lib/sync-queue.ts:38` `[VERIFIED]` backs each one off and `MAX_RETRY_COUNT = 5` marks it failed. Field captures are lost to a permission error that looks like a sync failure.

Prescribed, in this order, so the gap between the two states is never open:

1. Create `public.user_tenant_access` with its own RLS (a user reads only their own membership rows) in a migration *before* the policy migration. Splitting 003 into 003a/003b is the whole change.
2. Add `INSERT` and `UPDATE` policies. The `INSERT` policy needs `WITH CHECK`, and the `UPDATE` policy needs both `USING` and `WITH CHECK` with the same predicate — a `USING`-only `UPDATE` policy lets a tenant move a row it owns into another tenant's id, which is a write-side leak that a read-only test suite will never see.
3. Decide `DELETE` explicitly. Reports distributed to insurers are probably not tenant-deletable at all; the current grant says they are, and nobody chose that.
4. State what runs during the gap. The correct answer is almost certainly that writes are rejected for the duration rather than accepted unscoped, but that is a decision and the migration should record it.

The invariant to assert before merge, per the method's tenth position — verification is the work: run the cross-tenant read *and* the cross-tenant write as a genuinely authenticated non-owner session and confirm both are refused by the database. A test that only proves tenant A sees A's rows passes on a table with no policies at all, and is the positive control this repo is missing.
