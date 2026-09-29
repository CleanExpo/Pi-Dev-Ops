by: eng-authz
categories:
  invariants:    {state: PRESCRIBED, ref: "#tenant-isolation-is-a-stated-gate-with-no-enforcement-point", by: eng-authz, blocking: true}
  migration:     {state: PRESCRIBED, ref: "#the-tenancy-fix-cannot-apply-and-locks-everyone-out-when-it-does", by: eng-authz, blocking: true}
  failure_modes: {state: PRESCRIBED, ref: "#reports-are-written-by-a-role-that-rls-does-not-constrain", by: eng-authz, blocking: true}
cross_domain:
  - "003 is in the directory and not in the ledger — eng-release owns the ledger/directory disagreement; I own why the migration would fail if it were run"
  - "no test asserts a tenant A caller gets zero rows from a tenant B report — eng-test owns the oracle; the specific case is: authenticate as a user in tenant A, SELECT the id of a report in tenant B, assert 0 rows, and prove the test can fail by running it against migration 002 alone"
  - "AuditLog carries no tenantId and cascades away with its Inspection (lib/schema.prisma:20) — eng-data owns whether the audit trail may be deleted by a child cascade"
  - "the spec's other gate, 'A report may not be distributed unless its verification checklist is complete', has no column, table or code path anywhere in the fixture — eng-data owns where that state lives"

## Tenant isolation is a stated gate with no enforcement point

The spec names the invariant:

> Tenants must not read each other's reports.

Nothing in the repository enforces it, and the shape of what is deployed enforces the opposite.

`[VERIFIED]` `supabase/APPLIED_LEDGER.txt:1-2` contains exactly `001` and `002`. `[VERIFIED]` `supabase/migrations/002_policies.sql:3-4` — `CREATE POLICY "Anon read access" ON public.reports / FOR SELECT USING (true);` — and `002_policies.sql:6` — `GRANT SELECT, INSERT, UPDATE, DELETE ON public.reports TO anon, authenticated;`. `[INFERENCE]` A policy with no `TO` clause applies to `PUBLIC`, so `USING (true)` grants every role that holds the table grant an unfiltered read. Combined with the grant to `anon`, anyone holding the project's publishable anon key can `GET /rest/v1/reports` and receive every tenant's rows. `tenant_id` exists as a column (`001_init.sql:3` — `tenant_id uuid NOT NULL,`) and is referenced by no predicate that is live.

`[VERIFIED]` `grep -rni "tenant" .` returns hits in only four places: the spec line above, the `tenant_id` column in `001`, migration `003`, and `tenantId String` at `lib/schema.prisma:10`. There is no query layer, no Supabase client construction, and no `WHERE tenant_id` in any TypeScript file. So the invariant is not enforced in the database *and* is not enforced in application code — there is currently no code that could enforce it.

**Prescription.** State the invariant as three assertions that can be tested, not one sentence of intent, and pick one enforcement point per assertion:

1. A caller authenticated as a member of tenant A receives zero rows for any report whose `tenant_id` is not A, on every path — REST, RPC, view, background job, and report distribution.
2. A caller cannot write a row stamped with a `tenant_id` they are not a member of. This needs an `INSERT`/`UPDATE` policy with a `WITH CHECK` clause, not just `USING`; `003` supplies neither, so today the write half of the invariant is unstated.
3. The tenant identity used in the predicate is derived server-side from the session (`auth.uid()` and a membership table), never read from a request header, body field, or an unverified claim.

Grounded in: `USING (true)` plus a grant to `anon` is not a permissive default, it is a public table; and an invariant with no assertion attached to it cannot be regression-tested, which is why `002` survived `003` being written.

## The tenancy fix cannot apply and locks everyone out when it does

`[VERIFIED]` `supabase/migrations/003_rls_fix.sql:6` reads:

> `USING (tenant_id IN (SELECT tenant_id FROM public.user_tenant_access WHERE user_id = auth.uid()));`

`[VERIFIED]` `grep -rn "user_tenant_access" .` returns exactly one hit — that line. No migration creates that table; `001_init.sql` creates only `public.reports`.

`[INFERENCE]` `CREATE POLICY` parses and plans its `USING` expression at creation time, so `003` aborts with `relation "public.user_tenant_access" does not exist` before `DROP POLICY IF EXISTS` … actually the `DROP` at line 2 runs first and commits or not with the transaction; either way the `CREATE` fails and the migration does not complete. This is the most likely reason `003` is absent from the ledger, and it means the tenancy fix has never been one deploy away from landing — it has never been runnable. Re-running the deploy any number of times leaves `002` in force.

**What runs during the gap, and what happens when the gap closes.** Two things need designing before this is code:

- **The membership table is the missing half of the change.** `user_tenant_access (user_id, tenant_id)` must be created, seeded, and itself protected — it is now the table that decides who sees what, so it needs its own RLS (a user may read only their own membership rows) and a unique constraint on `(user_id, tenant_id)`. A membership table left world-readable or world-writable relocates the vulnerability rather than fixing it.
- **There is no backfill, so the fix is a total outage on read.** The moment a working `003` lands, the predicate returns rows only for users who already have a membership row. With an empty `user_tenant_access`, every authenticated user sees zero reports — including their own. The observable symptom is indistinguishable from data loss, at 3am, and the fastest-looking remedy is to restore `USING (true)`. Sequence it as: create and seed `user_tenant_access` from the existing distinct `(owner, tenant_id)` pairs in a migration that runs *before* the policy swap; verify the seed row count equals the expected user count; only then swap the policy.

`[UNCONFIRMED]` I cannot see the live database from here. The exact check for what is actually deployed:
`SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname IN ('reports','user_tenant_access');` and `SELECT tablename, policyname, cmd, roles, qual, with_check FROM pg_policies WHERE tablename = 'reports';`

## Reports are written by a role that RLS does not constrain

`[VERIFIED]` No migration in `supabase/migrations/` contains `FORCE ROW LEVEL SECURITY` — `grep -rni "force" .` returns nothing. `002_policies.sql:1` sets only `ALTER TABLE public.reports ENABLE ROW LEVEL SECURITY;`.

`[INFERENCE]` Without `FORCE`, the table owner is exempt from its own policies. In a Supabase project the migration role owns `public.reports`, and `service_role` carries `BYPASSRLS` besides. So every policy in this directory — the live permissive one and the intended strict one — is evaluated only for `anon` and `authenticated`. Any server-side path that uses the service key sees all tenants unconditionally.

That matters here specifically because of what the spec says the server does:

> Technicians capture readings offline; the server generates a report that is distributed to insurers.

Report generation and distribution are server-side, and `lib/sync-queue.ts:33` posts entries to `entry.endpoint` from the client with no tenant assertion visible on either side. `[VERIFIED]` `lib/sync-queue.ts:33` — `const response = await fetch(entry.endpoint, {`. The endpoint that receives those posts is not in this fixture, so the role it connects as is undetermined — and that is the whole question. **A report distributed to the wrong insurer is a cross-tenant disclosure that no RLS policy in this repo would have prevented**, because the generating path is exactly the path RLS does not cover.

The failure travels further than a single read: a misattributed report leaves the system entirely, into an insurer's inbox, where no rollback in the database reaches it. `lib/notify.ts:4` is explicitly fire-and-forget (`[VERIFIED]` `lib/notify.ts:2-3` — `reports errors loudly but never throws, so callers do not fail.`), so the send path has no failure signal a caller could use to hold a bad distribution back.

**Prescription.**

1. Add `ALTER TABLE public.reports FORCE ROW LEVEL SECURITY;` in the same migration as the policy, so the owner is not exempt and the policies you review are the policies that run.
2. Decide explicitly which paths may use the service key. Report generation should read as the requesting user wherever possible; where it genuinely needs elevated rights, the tenant scope must be an explicit parameter that is derived server-side and asserted before the row is written or sent, and that assertion should be a single chokepoint function rather than repeated per call site.
3. Record, per request path (REST, sync-queue endpoint, generation job, distribution job), which database role it executes as. That table is the artefact — the reason `002` shipped is that nobody had one.
