by: eng-authz
categories:
  invariants:  {state: PRESCRIBED, ref: "#tenant-isolation-is-enforced-nowhere-that-runs", by: eng-authz, blocking: true}
  migration:   {state: PRESCRIBED, ref: "#the-rls-fix-cannot-apply-as-written", by: eng-authz, blocking: true}
  test_oracle: {state: PRESCRIBED, ref: "#no-cross-tenant-read-probe-exists", by: eng-authz, blocking: true}
cross_domain:
  - "the applied ledger stops at 002 while the directory holds 003 — eng-release owns the ledger process; I am only claiming the authorisation consequence"
  - "nothing emits a signal when a report is read by a principal outside its tenant, so this class of breach is silent until an insurer reports it — eng-observability owns detection"
  - "public.user_tenant_access is referenced by a policy but declared in no migration and in no ORM model — eng-data owns whether that table is supposed to exist and who writes it"

## tenant-isolation-is-enforced-nowhere-that-runs

The spec states the invariant:

> Tenants must not read each other's reports.

It is stated and nowhere enforced. State is `PRESCRIBED`, not `DECIDED`, because the spec names the prohibition and never names the enforcement point, and every enforcement clause below is mine, not the author's.

What is actually live: the ledger records only two migrations — `supabase/APPLIED_LEDGER.txt:1-2`, `001` and `002` — so the policy in force is `supabase/migrations/002_policies.sql:3-4`, `CREATE POLICY "Anon read access" ON public.reports` / `FOR SELECT USING (true);`, alongside `002_policies.sql:6`, `GRANT SELECT, INSERT, UPDATE, DELETE ON public.reports TO anon, authenticated;` `[VERIFIED]`. RLS is on (`002_policies.sql:1`) and the only policy is unconditionally true, so enabling it bought nothing. Concretely: any holder of the anon key — which ships to the browser — issues `select * from reports` and receives every tenant's `body` jsonb. `003_rls_fix.sql:8`, `REVOKE ALL ON public.reports FROM anon;`, is the line that closes this, and it is in the directory, not in the database `[VERIFIED]`.

Three assertions someone can test, none of which hold today:

1. A principal authenticated as tenant A, selecting `public.reports` with no predicate, returns zero rows belonging to tenant B. Fails now: the `USING (true)` policy returns all rows.
2. The `anon` role has no privilege on `public.reports` at all. Fails now: `002_policies.sql:6` grants it `SELECT, INSERT, UPDATE, DELETE`.
3. A principal authenticated as tenant A cannot insert or update a row whose `tenant_id` is tenant B's. Fails after `003` too, and this is the part nobody has looked at: `003` adds a policy `FOR SELECT TO authenticated` (`003_rls_fix.sql:5`) and nothing else, while the `INSERT`, `UPDATE` and `DELETE` grants from `002:6` survive untouched — `003:8` revokes from `anon` only `[VERIFIED]`. Two branches, both unreviewed. If the API writes as `authenticated`, RLS with a grant but no `INSERT` policy denies every write, and offline capture fails closed the moment `003` lands. If the API writes with a service-role key or as the table owner, RLS is not evaluated at all on the write path and `tenant_id` is whatever the payload said `[INFERENCE]` — `lib/sync-queue.ts:33-37` POSTs `entry.payload` verbatim to `entry.endpoint` with no server-side re-derivation visible in this repo, so the tenant identifier is client-supplied unless a handler I cannot see re-stamps it.

I cannot tell which branch is real from here: no Supabase client, connection string, or `SERVICE_ROLE` reference exists anywhere in the fixture `[UNCONFIRMED]` — `grep -rn "SERVICE_ROLE\|createClient\|DATABASE_URL" .` returns nothing, and the question is settled by `SELECT current_user, session_user;` inside a request, plus `SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname='reports';`.

Prescription, grounded in the failure mechanism above rather than in any decision the author made:

- Add explicit `INSERT` and `UPDATE` policies with a `WITH CHECK` on the same tenant predicate. A `USING`-only `UPDATE` policy lets a row be read as tenant A and written back stamped tenant B.
- `ALTER TABLE public.reports FORCE ROW LEVEL SECURITY;`. Without it the owning role bypasses every policy, and migrations run as the owner, so any owner-connected path — a backfill, an admin script, a definer view — launders the check away.
- Decide, and write down, which database role serves requests. If it is the service role, tenant scoping is application code only and the invariant above is untestable at the database, which contradicts the spec gate.
- `tenant_id` must be re-derived server-side from the session, never read from the request body. `001_init.sql:2` declares `tenant_id uuid NOT NULL` with no default and no derivation `[VERIFIED]`, so whatever writes the row chooses its value.

## the-rls-fix-cannot-apply-as-written

`003_rls_fix.sql:6` predicates on `public.user_tenant_access`: `USING (tenant_id IN (SELECT tenant_id FROM public.user_tenant_access WHERE user_id = auth.uid()))` `[VERIFIED]`. That table is created by no migration in `supabase/migrations/` and appears in no model in `lib/schema.prisma` `[VERIFIED]` — `grep -rn user_tenant_access .` matches only that one policy line. Postgres resolves the relation at `CREATE POLICY` time, so this statement raises `relation "public.user_tenant_access" does not exist`.

That makes the ordering in the file the whole finding. `003:2` is `DROP POLICY IF EXISTS "Anon read access" ON public.reports;` and the failing `CREATE POLICY` is at `003:4` `[VERIFIED]`. Two outcomes during the gap, and which one you get depends on transaction handling nobody has stated:

- Wrapped in a transaction (Supabase CLI default): the drop rolls back, `003` is marked failed, and the permissive `USING (true)` policy stays live. The isolation hole persists and now looks like a deploy problem rather than a security one, which is how it survives a second sprint `[INFERENCE]`.
- Run statement-by-statement (psql without `--single-transaction`, a paste into the SQL editor, a partial retry after a timeout): the drop succeeds, the create fails, and the table is left with RLS enabled and zero policies. Every read returns zero rows for every principal that is not the owner. Reports vanish for all tenants simultaneously; the service-role and owner paths keep working, so a smoke test run from the server says healthy while every user sees an empty list `[INFERENCE]` — this is the failure I have actually been paged for, because the operator's instinct at 3am is to restore reads by re-adding a permissive policy.

Even once `user_tenant_access` exists, the predicate is not finished. RLS policy expressions are evaluated with the invoking user's privileges, so `authenticated` needs `SELECT` on `user_tenant_access` for the policy to evaluate at all — and granting that leaks the entire user-to-tenant mapping to every logged-in user unless that table carries its own RLS policy scoped to `auth.uid()`. Prescribe: create `user_tenant_access` with RLS and a self-scoped policy in the same migration that creates the reports policy, or wrap the lookup in a `SECURITY DEFINER` function with a pinned `search_path` and grant execute on that instead.

Prescribe also that `003` be a single transaction with the table creation ahead of the policy, so the permissive policy is never dropped in a state where its replacement failed. eng-release will likely answer this category too from the ledger side; I am answering the authorisation-specific half and do not contradict them.

## no-cross-tenant-read-probe-exists

The only test in the repo is `__tests__/engine.test.ts`, which asserts `expect(classify({ source: "sewage" }).category).toBe(3);` `[VERIFIED]`. Nothing exercises a policy. The spec's own done-condition — `Tests gate the classification engine.` — scopes testing to the engine, so the isolation gate has no oracle by construction, and every claim about it so far in this review is unfalsifiable by anything in CI.

An isolation invariant asserted only in prose is the one that regresses, because the regression is invisible: dropping a policy makes no test go red. What proves it, and what would have caught both findings above:

- Two authenticated sessions, tenants A and B, each with a seeded report. Assert session A's unfiltered `select * from reports` returns exactly its own row and that B's id is absent. Assert the same for an anon-key client, which must return zero rows or a permission error.
- A write probe: session A attempts `insert into reports (tenant_id, body) values ('<B>', '{}')` and must be rejected. This is the assertion that fails today and would still fail after `003`, since `003` adds no `INSERT` policy.
- A structural probe that does not need seeded data and costs one query: `SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname='reports'` must return `t, t`, and `SELECT cmd, count(*) FROM pg_policies WHERE tablename='reports' GROUP BY cmd` must show a policy for each of `SELECT`, `INSERT`, `UPDATE`. Run against the deployed database, not against the migration files — the gap between the two is exactly this change's defect.

Run these as a post-deploy check against the real database rather than a local reset, or they prove only that the directory is correct while production runs `002`.
