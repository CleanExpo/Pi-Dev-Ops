by: eng-authz
contributed: [eng-authz]
categories:
  invariants:    {state: PRESCRIBED, ref: "#tenant-isolation-is-unenforced-in-the-live-database", by: eng-authz, blocking: true}
  failure_modes: {state: PRESCRIBED, ref: "#migration-003-cannot-apply-and-if-it-did-all-writes-would-stop", by: eng-authz, blocking: true}
  test_oracle:   {state: PRESCRIBED, ref: "#the-negative-test-that-proves-isolation", by: eng-authz}
  interface_contract: {state: "N/A", reason: "No route handler, resolver, or client in this repo reads or writes public.reports, so there is no caller-facing shape whose change I could assess from here — the only surface touching tenancy is the SQL."}
cross_domain:
  - "003 is merged but absent from the applied ledger while 001 and 002 are present — eng-release owns the ledger-versus-directory divergence itself"
  - "public.reports has no verification-checklist column, so the spec's distribution gate has no column to test — eng-data owns the shape"
  - "schema.prisma carries Inspection.tenantId but AuditLog has no tenant column and reaches tenancy only through its parent — eng-data owns whether that join is the intended ownership path"

*Method note: my instinct is to prescribe a full session-variable plus dedicated non-owner role architecture. Method 1 wins — the boring version (create the missing table, add the write policies, one cross-tenant test) is untried here, so that is what I prescribe.*

## Tenant isolation is unenforced in the live database

The spec states the invariant plainly:

> Tenants must not read each other's reports.

Nothing in the database currently enforces it. The applied ledger stops at 002 `[VERIFIED]` — `supabase/APPLIED_LEDGER.txt:1-2` contains exactly `001` and `002` — so the live policy set is the one 002 installs, which is:

> `CREATE POLICY "Anon read access" ON public.reports FOR SELECT USING (true);`
> — `supabase/migrations/002_policies.sql:3-4`

paired with

> `GRANT SELECT, INSERT, UPDATE, DELETE ON public.reports TO anon, authenticated;`
> — `supabase/migrations/002_policies.sql:6`

`USING (true)` is a policy that evaluates to true for every row for every role it applies to, and 002 names no role, so it applies to `PUBLIC` — including `anon`. RLS is enabled, which makes the table *look* protected in `pg_class.relrowsecurity`, and the single permissive policy then returns every tenant's rows to every caller, authenticated or not `[VERIFIED]` from the two lines above. The repo reads as tenant-scoped because 003 exists in the directory; the running system is 002.

The prescription, as testable assertions:

1. **No role may hold a blanket-true predicate on `public.reports`.** `SELECT polname, roles, pg_get_expr(polqual, polrelid) FROM pg_policy WHERE polrelid = 'public.reports'::regclass` must return zero rows whose predicate is `true`. `[UNCONFIRMED]` — run that query against the live database now; it is the fastest way to learn whether this is currently a live cross-tenant read.
2. **`anon` holds no privilege on `public.reports`.** 003 revokes it (`REVOKE ALL ON public.reports FROM anon;` — `supabase/migrations/003_rls_fix.sql:8`) `[VERIFIED]`, but 003 has not run, so today `anon` holds all four DML privileges. Until 003 or an equivalent lands, an unauthenticated caller holding only the publishable anon key can read every report in the system.
3. **`FORCE ROW LEVEL SECURITY` is set, not merely `ENABLE`.** No migration sets it — `grep -rn "FORCE ROW LEVEL" .` returns nothing across the fixture `[VERIFIED]`. Without it the table owner is exempt, and every policy in this repo is invisible to any connection made as the owner. This is the question my seat exists to ask: which role does the request execute as? The repo contains no database client at all, so I cannot answer it from here `[UNCONFIRMED]` — read the connection string's role, and if the server generating and distributing reports uses a Supabase `service_role` key, RLS is bypassed outright on that path and *none* of this SQL constrains the server. `[INFERENCE]` — this is the specific way I have seen correct-looking policy sets enforce nothing: the policies are real, and the only code path that matters never evaluates them.

## Migration 003 cannot apply and if it did all writes would stop

Two failures, both concrete.

**It aborts on a table that does not exist.** 003's predicate reads:

> `USING (tenant_id IN (SELECT tenant_id FROM public.user_tenant_access WHERE user_id = auth.uid()));`
> — `supabase/migrations/003_rls_fix.sql:6`

`grep -rn "CREATE TABLE" .` returns exactly one hit, `supabase/migrations/001_init.sql:1`, creating `public.reports` `[VERIFIED]`. `public.user_tenant_access` is referenced once and created nowhere `[VERIFIED]`. `CREATE POLICY` parses and resolves its expression at definition time, so this statement raises `relation "public.user_tenant_access" does not exist` and the migration fails `[INFERENCE]` — which is the most likely reason the ledger stops at 002 rather than an operator forgetting. The failure mode that matters is the ordering: 003 drops the permissive policy *before* it creates the replacement (`DROP POLICY IF EXISTS "Anon read access"` at line 2, `CREATE POLICY` at line 4). Outside a transaction, the drop commits and the create aborts, leaving RLS enabled with **zero** policies and every read returning empty — a total outage rather than a leak. Prescribe: create `public.user_tenant_access` in a migration ordered before 003, and require every policy migration to run inside an explicit `BEGIN`/`COMMIT` so a half-applied policy set is not reachable.

**It covers `SELECT` only.** 003 creates one policy, `FOR SELECT TO authenticated` (line 5) `[VERIFIED]`, and revokes only from `anon` (line 8) `[VERIFIED]` — `authenticated` keeps the `INSERT, UPDATE, DELETE` grant from 002. With RLS enabled and no policy for a command, that command is denied by default, so the moment 003 succeeds every technician write to `public.reports` starts failing `[INFERENCE]`. This fails closed, which is the right direction, but it is a silent decision: nobody wrote down that writes were out of scope. Prescribe explicitly, because the `USING`/`WITH CHECK` split is where the leak actually lives:

- `INSERT` policy with a `WITH CHECK` on the same tenant predicate — without it a caller stamps a row with any `tenant_id` they choose and writes into another tenant's data.
- `UPDATE` policy with **both** `USING` and `WITH CHECK`. A `USING`-only `UPDATE` policy restricts which rows you may target but not what you may set them to, so a tenant can take a row they legitimately own and move it to another tenant's id.
- `DELETE` policy, or revoke the `DELETE` grant if technicians are never meant to delete.

I would be wrong about the write breakage if the writing path connects as the owner or `service_role`, in which case writes keep working and the isolation finding above gets worse instead — the same unanswered question decides both.

## The negative test that proves isolation

There is no test that touches tenancy. `__tests__/engine.test.ts` contains a single case asserting `classify({ source: "sewage" }).category` is `3` `[VERIFIED]`, and nothing else in the repo exercises the database.

A passing suite is not evidence that isolation holds, and a green run against a table with `USING (true)` looks identical to a green run against a correct policy set — every read succeeds either way. The oracle has to be a **negative** test with a positive control:

1. Seed two tenants, A and B, each with one report.
2. Connect as a real end-user JWT for tenant A **through the same client and role the application uses** — not a service key, not the owner. If the test harness uses a privileged key, it proves nothing, and that is the single most common way this test passes while production leaks.
3. Assert the read returns exactly A's row and that B's id is absent.
4. Assert an `INSERT` and an `UPDATE` stamping `tenant_id = B` are both rejected.
5. **Positive control:** temporarily restore a `USING (true)` policy in the test fixture and assert step 3 *fails*. A cross-tenant test that has never been seen to fail is not known to be capable of failing.

Per method 6, this recurs, so it should be a check rather than a review comment: assert in CI that every table in `public` has `relrowsecurity` and `relforcerowsecurity` true and at least one policy per command it grants — `SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class JOIN pg_policies ...`. That single query is the cheapest thing that distinguishes "protected" from "protected in the diff", and running it against the live database is what closes every `[UNCONFIRMED]` above.
