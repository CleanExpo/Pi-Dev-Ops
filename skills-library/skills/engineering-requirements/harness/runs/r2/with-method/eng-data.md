by: eng-data
contributed: [eng-data]
categories:
  data_model: {state: PRESCRIBED, ref: "#ownership-is-a-bare-uuid-with-nothing-to-reference", by: eng-data, blocking: true}
  migration:  {state: PRESCRIBED, ref: "#migration-003-is-unapplied-and-unrunnable", by: eng-data, blocking: true}
  invariants: {state: PRESCRIBED, ref: "#the-distribution-gate-has-no-column-to-live-in", by: eng-data, blocking: true}
cross_domain:
  - "the live predicate is `FOR SELECT USING (true)` granted to anon — whether that is a disclosure incident, not just drift, is eng-authz's call"
  - "003's USING clause runs a correlated subquery per row on an unindexed `reports.tenant_id` — eng-performance owns the index"
  - "if 003 is applied non-transactionally the DROP lands and the CREATE fails, leaving RLS on with zero SELECT policies and all reads denied — eng-rollback owns the recovery sequence"
  - "`reports.body jsonb` is the entire report payload with no shape enforced at the boundary — eng-contract owns whether it should be typed"

## Ownership is a bare uuid with nothing to reference

The same logical owner is stored in two disconnected places, and nothing in the database enforces that either one is real.

`reports` carries a tenant with no referent:

> `  tenant_id uuid NOT NULL,` — `supabase/migrations/001_init.sql:3` `[VERIFIED]`

`CREATE TABLE` appears exactly once in this repo — `001_init.sql:1`, for `public.reports`. There is no `tenants` table, no `user_tenant_access` table, and no `REFERENCES` or `FOREIGN KEY` anywhere in `supabase/migrations/` `[VERIFIED — grep over the fixture returns one CREATE TABLE and zero REFERENCES in .sql]`. So `tenant_id` is an unconstrained uuid: any write, including a bug that writes `gen_random_uuid()` or a stale tenant, is accepted, and no query will ever surface it because there is no parent to be orphaned from.

The second copy lives in the ORM, also unconstrained:

> `  tenantId  String` — `lib/schema.prisma:10` `[VERIFIED]`

`Inspection.tenantId` is a plain `String` with no `@relation`, while `userId` on the same model does have one. No model in `schema.prisma` references `reports`, and no migration references `Inspection`. The two halves of this system therefore disagree about what a tenant is (uuid vs String) and there is no FK spanning them, so nothing detects divergence. This is the failure my seat exists for: an owner recorded twice and reconciled nowhere.

Now the cascade question. Deleting one `User` row runs a two-hop hard cascade:

> `  user      User       @relation(fields: [userId], references: [id], onDelete: Cascade)` — `lib/schema.prisma:11` `[VERIFIED]`
> `  inspection   Inspection @relation(fields: [inspectionId], references: [id], onDelete: Cascade)` — `lib/schema.prisma:20` `[VERIFIED]`

`AuditLog` is reachable only through `Inspection`, and `Inspection` only through `User`. One `DELETE FROM users WHERE id = ...` — a GDPR erasure request, a deduplication script, a test fixture teardown pointed at the wrong database — silently destroys every audit record for that technician's inspections, including records that exist precisely to prove what happened after the person is gone `[INFERENCE — this is the standard shape; I have seen an erasure job take the audit trail with it, and the loss is invisible because the evidence of the deletion was in the deleted rows]`. Nothing in the repo soft-deletes: there is no `deleted_at` column and no occurrence of the string anywhere `[VERIFIED — grep for deleted_at over the fixture returns nothing]`.

**Prescription.**

1. Create the tenant parent before anything else references it. `reports.tenant_id` gets `REFERENCES public.tenants(id)`; `Inspection.tenantId` becomes a `@relation` to the same table and changes type to match the uuid. Two representations of one owner is the defect; pick one.
2. Decide `reports` → `inspections` explicitly. Today a report is not linked to the inspection that produced it in either schema. If that link is intended, it is a FK with a stated `ON DELETE`; if it is genuinely absent, say so in the spec, because a report whose source inspection can be deleted independently is a report nobody can substantiate.
3. Change `AuditLog.inspection` from `onDelete: Cascade` to `onDelete: Restrict` (or `SetNull` on a nullable `inspectionId`, keeping the row). An audit log that a parent delete can remove is not an audit log. If regulatory erasure must still work, it anonymises the log's subject fields; it does not delete the log.
4. Because `tenant_id` is `NOT NULL` and about to gain an FK, the FK must be added `NOT VALID` and validated in a second statement — `ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY ... NOT VALID;` then `ALTER TABLE ... VALIDATE CONSTRAINT ...;`. Added in one step it takes `ACCESS EXCLUSIVE` and a full scan of `reports`, which is fine on the empty dev table and is minutes of blocked writes once insurers' reports are in it `[INFERENCE — standard PG lock behaviour; unverifiable here because the table is empty]`.
5. Backfilling existing `reports` rows to real tenants is not a single `UPDATE`. Batch on `created_at` or `id` ranges, make it re-runnable to the same result, and keep the rows it could not resolve visible rather than defaulting them into some tenant — a mis-resolved row here is a cross-tenant disclosure, which is the exact thing the spec's third gate forbids.

**What would overturn this:** a `tenants` table and a `user_tenant_access` table that exist in the deployed database but were created outside `supabase/migrations/` — in which case the finding is unchanged in substance and becomes schema drift, and the prescription is to capture them into migrations rather than to create them. `[UNCONFIRMED — settle it with psql -c '\dt public.*' against the deployed database, or SELECT table_name FROM information_schema.tables WHERE table_schema='public', and diff the result against supabase/migrations/.]`

## Migration 003 is unapplied and unrunnable

Two separate defects, and fixing only the first makes the outage.

**It has never been applied.** The ledger records two migrations:

> `001` / `002` — `supabase/APPLIED_LEDGER.txt:1-2` `[VERIFIED — the file is two lines; there is no 003]`

while the directory holds three: `001_init.sql`, `002_policies.sql`, `003_rls_fix.sql` `[VERIFIED]`. The deployed database is therefore still running what 002 installed:

> `CREATE POLICY "Anon read access" ON public.reports` / `  FOR SELECT USING (true);` — `supabase/migrations/002_policies.sql:3-4` `[VERIFIED]`

003's own comment states what it is for — *"Tenant-scoped replacement for the permissive policy in 002"* (`003_rls_fix.sql:1`) — so this is a migration that was started and not finished. The system now has two truths, the repo's and the database's, and no rule for which wins. Method position 4 is explicit that this state is worse than either end state.

**Applying it as written will fail.** The policy body selects from a table this repo never creates:

> `  USING (tenant_id IN (SELECT tenant_id FROM public.user_tenant_access WHERE user_id = auth.uid()));` — `supabase/migrations/003_rls_fix.sql:6` `[VERIFIED]`

`public.user_tenant_access` appears exactly once in the entire fixture — on that line `[VERIFIED — grep for user_tenant_access returns one hit]`. Postgres resolves the relations in a policy expression at `CREATE POLICY` time, so this statement raises `relation "public.user_tenant_access" does not exist` and the migration aborts `[INFERENCE — policy expressions are parsed and analysed on creation, not deferred to first use; confirm with psql -1 -f supabase/migrations/003_rls_fix.sql against a scratch database that has had 001 and 002 applied]`.

The ordering is what makes this dangerous rather than merely broken. The file drops before it creates:

> `DROP POLICY IF EXISTS "Anon read access" ON public.reports;` — `supabase/migrations/003_rls_fix.sql:2` `[VERIFIED]`

If the runner wraps the file in a transaction, the abort rolls the drop back and prod stays wide open — the failure is loud and harmless. If it does not, the drop and the `REVOKE ALL ON public.reports FROM anon;` on line 8 commit and the `CREATE POLICY` does not, leaving RLS enabled with no SELECT policy: every read returns zero rows and the reporting product looks empty rather than broken `[INFERENCE]`.

**Prescription.**

1. Do not apply 003 in its current form. Ship `004_user_tenant_access.sql` creating `public.user_tenant_access (user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE, tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE, PRIMARY KEY (user_id, tenant_id))`, populate it, then apply the policy — dependency before dependent, in that order.
2. Re-order the policy migration to create the replacement first and drop the permissive policy last, in one explicit transaction, so no window exists in which `reports` has RLS enabled and no readable policy.
3. Add a CI check that fails the build when `supabase/migrations/` contains a file the ledger does not list. This is method position 6: the drift is not the finding, the absence of the check is. Under the current arrangement the only thing standing between a permissive prod policy and a fix is somebody remembering.
4. Give the ledger a schema-hash column, not just a filename list. A filename list cannot detect a migration applied by hand through the SQL console, which is how declared and deployed schema usually diverge.

**Where the method beat my instinct:** my reflex was to write the missing table and get 003 landed. Method position 4 says the deliverable is the abandoned migration itself — the ledger is a second source of truth that nothing reconciles, and shipping 004 without the check in point 3 leaves the mechanism that produced this defect fully intact.

**Note for the chair:** eng-release is dispatched unconditionally on ledger/directory disagreement and will file the same drift. We do not conflict — their half is that the pipeline cannot tell you 003 never applied; mine is that applying it in this order is itself the outage.

## The distribution gate has no column to live in

The spec's first gate is:

> `- A report may not be distributed unless its verification checklist is complete.` — `spec.md:8` `[VERIFIED]`

`public.reports` has four columns — `id`, `tenant_id`, `body jsonb NOT NULL`, `created_at` — and that is the whole table `[VERIFIED — supabase/migrations/001_init.sql:1-6]`. There is no checklist column, no completeness flag, no distribution state, and no distributed-at timestamp; `grep -i` over the `.sql` and `.prisma` files finds no occurrence of `checklist`, `verif`, or `distribut` outside `spec.md` `[VERIFIED]`.

So the invariant cannot be stated as an assertion anyone could test against a row. Concretely: two operators open the same report, one marks the checklist complete inside the `body` blob while the other triggers distribution — there is no column to take a lock on, no `CHECK` to violate, and no state transition to make illegal. Whatever enforces this gate lives in application code, and the first path that forgets to call it (a retry, a bulk-send, a support script, an agent writing the second caller) distributes an unverified report to an insurer with no record that it happened `[INFERENCE — a gate held only in application code is a gate held once per caller; every system I have seen enforce a "must be complete before send" rule in code alone eventually grew a second sender]`.

`jsonb` makes this worse than merely unenforced: because completeness lives inside `body`, "the checklist is complete" is not queryable without a functional index, cannot be constrained, and has no schema — so two writers can disagree about the key's name and both be accepted.

**Prescription.** Lift the gate out of the blob into columns the database can defend:

- `checklist_completed_at timestamptz NULL` and `distributed_at timestamptz NULL` on `reports`.
- `CONSTRAINT distribution_requires_verification CHECK (distributed_at IS NULL OR checklist_completed_at IS NOT NULL)` — this is the spec sentence, transcribed. It is method position 8: make the illegal state unrepresentable rather than unreached.
- Distribution sets `distributed_at` via a conditional update (`UPDATE ... SET distributed_at = now() WHERE id = $1 AND distributed_at IS NULL AND checklist_completed_at IS NOT NULL`), and the sender treats zero affected rows as "someone else already sent it, stop" — that is what makes a retried send safe.
- Add the `CHECK` as `NOT VALID` and validate separately, for the same lock reason as the FK above.
- Existing rows: every current `reports` row predates the gate and cannot be assumed verified. Backfill `checklist_completed_at` to `NULL`, not to `created_at`. Defaulting them to verified is the silent decision that turns a schema change into a compliance problem.

**Note for the chair:** `invariants` is a cross-cutting category and eng-test or eng-failure may also claim it. I am claiming only the half my lane owns — that the invariant has no representation in the schema and therefore no enforceable form. What proves the application honours it is the test seat's, and I do not contradict them.
