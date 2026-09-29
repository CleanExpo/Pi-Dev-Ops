by: eng-authz
categories:
  invariants:    {state: PRESCRIBED, ref: "#invariants-nobody-enforces", by: eng-authz, blocking: true}
  failure_modes: {state: PRESCRIBED, ref: "#the-applied-state-serves-every-tenant-to-anyone", by: eng-authz, blocking: true}
cross_domain:
  - "003 sits in migrations/ but not in APPLIED_LEDGER.txt, and as written it cannot apply — eng-release owns the ledger-vs-directory disagreement"
  - "public.user_tenant_access is referenced but created by no migration; the reports/Inspection split has no shared tenant table — eng-data owns the schema"
  - "the only test covers classify(); nothing asserts a cross-tenant read is refused — eng-test owns the oracle"
  - "whether the app holds a service-role key at all, and where it is scoped — eng-secrets owns key custody"

## Invariants nobody enforces

The spec states two authorisation invariants and stops there:

> - A report may not be distributed unless its verification checklist is complete.
> - Tenants must not read each other's reports.

Neither exists anywhere below the spec. `grep -rniE "checklist|verif|distribut"` across the whole fixture returns only those two spec lines — no column, no policy, no code `[VERIFIED]`. The `reports` table is `id, tenant_id, body, created_at` `[VERIFIED: supabase/migrations/001_init.sql:1-6, "body jsonb NOT NULL,"]`, so there is no state a checklist gate could even read. An invariant with no representation is a sentence, not a gate.

State them as assertions someone can run, and put each at a boundary the database evaluates:

1. **`SELECT` on `reports` as tenant A's JWT returns zero rows written by tenant B.** Today the applied policy is `USING (true)` — see the next section.
2. **`INSERT`/`UPDATE` on `reports` cannot stamp a `tenant_id` the caller does not hold.** No write policy exists in any migration; 003 creates `FOR SELECT` only `[VERIFIED: supabase/migrations/003_rls_fix.sql:5, "FOR SELECT TO authenticated"]`, and 002 grants `INSERT, UPDATE, DELETE` to `authenticated` `[VERIFIED: supabase/migrations/002_policies.sql:6, "GRANT SELECT, INSERT, UPDATE, DELETE ON public.reports TO anon, authenticated;"]`. A `USING` clause without a matching `WITH CHECK` is the classic shape where a tenant reads only their rows and writes rows stamped with someone else's id.
3. **A `reports` row cannot be distributed while its checklist is incomplete.** Needs a real column (`checklist_complete boolean NOT NULL DEFAULT false`, or a `distributed_at` guarded by a `CHECK`/trigger). Enforced in the route handler alone it is laundered away by any second writer — and this repo already has one, see (4).
4. **The invariant holds on the Prisma plane too.** `Inspection` carries `tenantId String` with no relation and no policy `[VERIFIED: lib/schema.prisma:10, "tenantId  String"]`, and Prisma connects through a single pooled role that is normally the table owner. `ENABLE ROW LEVEL SECURITY` is set on `reports` `[VERIFIED: supabase/migrations/002_policies.sql:1, "ALTER TABLE public.reports ENABLE ROW LEVEL SECURITY;"]` but `FORCE ROW LEVEL SECURITY` is never set anywhere in the repo. The owner bypasses. So the tenancy story is enforced by the database on one path and by nothing at all on the other.

Grounding: these are the four assertions I have watched a multi-tenant Postgres deployment fail on, in that order. `[INFERENCE]` on the owner-bypass mechanism — I cannot see a connection string from here. The cheap confirmation, which a human must run because I am read-only: `SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname IN ('reports','Inspection');` joined against `pg_policies`, plus `SELECT current_user, rolbypassrls FROM pg_roles WHERE rolname = current_user;` executed on the *application's* connection, not a psql superuser session `[UNCONFIRMED]`.

## The applied state serves every tenant to anyone

This is not a future risk; it is the current production shape.

The ledger records two migrations `[VERIFIED: supabase/APPLIED_LEDGER.txt:1-2, "001\n002"]`. 002 is what is live, and 002 is:

`[VERIFIED: supabase/migrations/002_policies.sql:3-4, "CREATE POLICY \"Anon read access\" ON public.reports\n  FOR SELECT USING (true);"]`

`USING (true)` with no `TO` clause applies to every role, and 002 grants `SELECT` to `anon` `[VERIFIED: supabase/migrations/002_policies.sql:6, "GRANT SELECT, INSERT, UPDATE, DELETE ON public.reports TO anon, authenticated;"]`. Concrete scenario, no timing subtlety required: any holder of the public anon key — which ships to every browser — issues `GET /rest/v1/reports?select=*` and receives every tenant's report bodies. Enabling RLS and then writing a `true` predicate reads as protection in the diff and is a total bypass at runtime. Spec gate 3 is violated right now, in the deployed state.

The repair migration does not repair it. 003 is unapplied, and it also cannot apply as written: its predicate reads `public.user_tenant_access` `[VERIFIED: supabase/migrations/003_rls_fix.sql:6, "USING (tenant_id IN (SELECT tenant_id FROM public.user_tenant_access WHERE user_id = auth.uid()));"]` and that relation is created by no migration in the repo — `grep -rn user_tenant_access` matches that one line and nothing else `[VERIFIED]`. Run inside a transaction it aborts on `relation does not exist` and rolls back, so the `DROP POLICY IF EXISTS` on line 2 reverts and the permissive policy survives. Run statement-by-statement, the drop commits and the create fails: the table is then left with RLS enabled and **zero** policies, which denies `authenticated` reads outright while `anon`'s `REVOKE` on line 8 has not run — a different outage, reached by the same file. Either way the operator sees a failed migration and an unchanged or worse security posture `[INFERENCE]` on which branch, because it depends on how the runner wraps statements — name it: `supabase db push` wraps per-file, a raw `psql -f` without `ON_ERROR_STOP` does not.

Before 003 is retried it needs: `user_tenant_access` created and itself RLS-protected (otherwise the membership table is the new hole), `FORCE ROW LEVEL SECURITY` on `reports`, `REVOKE ALL ... FROM anon` moved ahead of the policy swap so the exposure closes even if the rest fails, and matching `INSERT`/`UPDATE` policies carrying `WITH CHECK` — note 003 revokes only from `anon`, leaving `authenticated` holding write grants with no write policy `[VERIFIED: supabase/migrations/003_rls_fix.sql:8, "REVOKE ALL ON public.reports FROM anon;"]`.

I expect `eng-failure` to also file under `failure_modes`; recording rather than overwriting — my half is specifically the authorisation blast radius (which role reads what), not the general failure surface.
