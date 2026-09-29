by: eng-authz
categories:
  invariants:    {state: PRESCRIBED, ref: "#tenant-isolation-is-unenforced-in-the-applied-state", by: eng-authz, blocking: true}
  failure_modes: {state: PRESCRIBED, ref: "#003-cannot-apply-and-if-it-did-it-would-revoke-every-write", by: eng-authz, blocking: true}
  test_oracle:   {state: PRESCRIBED, ref: "#the-runtime-role-probe-nobody-runs", by: eng-authz, blocking: true}
cross_domain:
  - "supabase/APPLIED_LEDGER.txt records 001 and 002 but migrations/ holds 003 — the ledger-vs-directory drift and what runs during the gap is eng-release's"
  - "003's predicate runs a correlated subquery per row against an unindexed reports.tenant_id (001 declares no index) — eng-performance owns the cost"
  - "lib/schema.prisma models Inspection/AuditLog that appear in no migration, so the repo has two schema truths — eng-data owns which one is authoritative"
  - "if the server reaches this table with a Supabase service-role key, every policy below is bypassed regardless of correctness — eng-secrets owns which credential the runtime holds"

## Tenant isolation is unenforced in the applied state

The spec states the gate as a sentence, not an assertion: `spec.md:11` — "> Tenants must not read each other's reports." Nothing in the repo turns that into something testable, and in the state the repo says is live it is false.

`supabase/APPLIED_LEDGER.txt:1-2` contains exactly `001` and `002` [VERIFIED]. So the policy actually in force is the one from `supabase/migrations/002_policies.sql:3-4` [VERIFIED]:

> `CREATE POLICY "Anon read access" ON public.reports`
> `  FOR SELECT USING (true);`

and the grant at `002_policies.sql:6` [VERIFIED]:

> `GRANT SELECT, INSERT, UPDATE, DELETE ON public.reports TO anon, authenticated;`

Concretely: technician A of tenant X issues `select * from reports` with any valid anon key. `USING (true)` is satisfied for every row, so tenant Y's reports return. There is no timing subtlety and no interleaving needed — it is the steady state. The same grant lets an unauthenticated `anon` `UPDATE` and `DELETE` any report in the table, which also destroys the checklist gate at `spec.md:10` from underneath, because a row's verification state is a column an anon role may write. Method §4 ("finish the migration you start") is why this is filed here rather than as a policy bug: `003_rls_fix.sql` is the second truth nobody retired, and the repo therefore reads as fixed while the database is wide open — my domain instinct was to file "the policy is wrong"; the method says the half-finished migration is the finding, and it wins.

The invariants that must be written down as assertions, none of which exist today [INFERENCE — greenfield for these assertions; nothing in the repo states them]:

1. **No read across tenants.** For any session, `select count(*) from reports where tenant_id <> <session tenant>` returns 0. Enforced by the database, not by a `where` clause in a handler.
2. **No write stamped with a foreign tenant.** An `INSERT` or `UPDATE` whose `tenant_id` is not the session's tenant is rejected. This needs a `WITH CHECK` clause; the repo contains none — `grep -rn "WITH CHECK"` over the fixture returns nothing [VERIFIED, empty result].
3. **The tenant identifier is server-derived.** It comes from `auth.uid()` resolved server-side, never from a request header, body field, or an unverified claim the server echoes back.
4. **No role bypasses.** `ENABLE ROW LEVEL SECURITY` alone leaves the table owner exempt. `grep -rn "FORCE ROW LEVEL"` returns nothing [VERIFIED, empty result], so if the application's connection role owns `public.reports` — the default when migrations and the app share one Postgres role — every policy below is skipped and assertion 1 is false even after 003 lands.

Prescription: add `ALTER TABLE public.reports FORCE ROW LEVEL SECURITY`, and state assertions 1–4 in the spec as the definition of gate 3 so a reviewer can check the policy against the assertion rather than against intent. What would overturn this: evidence that the runtime connects as a distinct non-owning role with `NOBYPASSRLS` and that the ledger is not the source of truth for what is applied.

## 003 cannot apply, and if it did it would revoke every write

Two separate mechanisms, both blocking, and the second is the one that will look like an outage.

**It cannot apply.** `supabase/migrations/003_rls_fix.sql:6` [VERIFIED]:

> `  USING (tenant_id IN (SELECT tenant_id FROM public.user_tenant_access WHERE user_id = auth.uid()));`

`grep -rn "user_tenant_access"` across the whole fixture returns that one line and nothing else [VERIFIED] — the table is created by no migration. `CREATE POLICY` resolves relation names at creation time, so `003` aborts with `relation "public.user_tenant_access" does not exist`. That is the most likely reason the ledger stops at `002`: the fix was written, the deploy failed, and the failure left the permissive policy from `002` in place. A migration that fails *open* is the worst shape available — the operator sees a red deploy, retries the app, and the table stays readable by everyone.

**If it applies, writes stop.** `003` creates one policy, `FOR SELECT` only (`003_rls_fix.sql:5` [VERIFIED]: `  FOR SELECT TO authenticated`). RLS is default-deny per command: with `ENABLE ROW LEVEL SECURITY` set at `002_policies.sql:1` and no `INSERT`, `UPDATE`, or `DELETE` policy anywhere, every write by `authenticated` is rejected even though `002` granted the privilege. The failure surfaces at the worst place in this product: `lib/sync-queue.ts:38` [VERIFIED] — `      if (!response.ok) await incrementRetry(db, entry);` — so a technician's offline captures do not error visibly, they retry five times against a permanent authorisation denial and then `markFailed` at `sync-queue.ts:28-30`, silently, on a device with no operator watching. Blast radius is every capture taken between the deploy and someone noticing, and the data is on handsets rather than in the database.

Prescription: create `public.user_tenant_access` (or replace the subquery with a JWT-independent server-derived claim) in a migration ordered *before* `003`; add `INSERT`/`UPDATE`/`DELETE` policies with matching `USING` **and** `WITH CHECK` predicates so a tenant can neither write a foreign `tenant_id` nor move a row into another tenant; and make the migration runner fail closed so a failed `003` does not leave `002`'s permissive policy serving traffic.

## The runtime role probe nobody runs

The only test in the repo is `__tests__/engine.test.ts`, and it does not run: `vitest.config.ts:3-6` includes only `lib/**/__tests__/**` and `app/**/__tests__/**` [VERIFIED], while the file sits at `./__tests__/engine.test.ts` [VERIFIED via `ls`]. Nothing tests authorisation at all. That is not a gap in coverage; for gate 3 it means the invariant has never once been observed to hold.

An authorisation test that runs in-process against mocked clients proves nothing here, because everything that fails above fails in the database, under a specific role. The oracle has to be a live probe:

1. **Which tables are actually protected** — `SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'reports'` joined against `pg_policies`, asserting `relforcerowsecurity` is true and that policies exist for all four commands. [UNCONFIRMED — I have no database from here; a human runs this against staging and production.]
2. **Which role the request executes as** — `select current_user, session_user, rolbypassrls from pg_roles where rolname = current_user`, executed *through the application's own connection*, not through psql as an admin. This is the question the rest of the review cannot answer: policies that are correct in `pg_policies` enforce nothing if the runtime is the owner or holds `BYPASSRLS`. [UNCONFIRMED — needs the app's live connection string.]
3. **The negative test that must fail** — seed two tenants, authenticate as tenant X, `select` and assert 0 rows of tenant Y; then attempt `insert into reports (tenant_id, body) values ('<Y>', ...)` and assert rejection. Run it as a positive control first by temporarily removing the policy in a scratch database and confirming the test goes red — a test that passes against an empty table looks identical to a test that passes against a correct policy.
4. **Assert the ledger matches the directory in CI**, so "003 is in the repo" can never again be mistaken for "003 is in the database". The mechanics of that check belong to eng-release; the reason it is blocking is mine.

Grounding: method §6 — this exact review comment (a policy that is right in the diff and absent at runtime) is one a human will make again next month, so the deliverable is the standing check, not the corrected policy. eng-test may also answer `test_oracle`; I am answering only the authorisation half and defer the classification-engine half to that seat.
