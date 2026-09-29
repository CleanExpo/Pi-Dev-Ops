by: eng-data
categories:
  data_model: {state: PRESCRIBED, ref: "#ownership-is-declared-twice-and-the-cascade-deletes-the-audit-trail", by: eng-data, blocking: true}
  migration:  {state: PRESCRIBED, ref: "#003-references-a-table-that-does-not-exist-and-was-never-applied", by: eng-data, blocking: true}
cross_domain:
  - "whether the 002 grants left on `anon` are exploitable, and whether the 003 predicate is the right tenancy predicate — eng-authz owns both"
  - "nothing in the pipeline compares supabase/APPLIED_LEDGER.txt against supabase/migrations/ — eng-release owns the drift detector"
  - "there is no down migration for 001, 002 or 003 and no way to reverse 003 once applied — eng-rollback owns the reversal path"
  - "no signal exists that a merged migration was never applied; the health route reports `status: ok` regardless — eng-observability owns detection"

*(All paths below are relative to the fixture root.)*

## Ownership is declared twice and the cascade deletes the audit trail

**Two unlinked ownership columns.** `reports` carries tenancy in SQL, `Inspection` carries it in Prisma, and nothing joins or constrains them.

[VERIFIED] `supabase/migrations/001_init.sql:3` — `  tenant_id uuid NOT NULL,`
[VERIFIED] `lib/schema.prisma:10` — `  tenantId  String`

No `tenants` table and no `user_tenant_access` table are created anywhere in the repo; `grep -rni tenant` over the fixture returns only these two column declarations, the spec sentence, and the 003 policy. So both columns are free-text/free-uuid with no referential integrity, and `reports` does not appear in the Prisma schema at all while `User`/`Inspection`/`AuditLog` have no migration that creates them. The two declared schemas do not share a single table — the ORM and the migration ledger are not two views of one database, they are two databases nobody has reconciled. Concrete divergence: a report written with `tenant_id = A` and an inspection written with `tenantId = 'a'` (or a stale tenant after a merge/rename) are the same logical row set to the application and different rows to every predicate; the 003 RLS policy filters on `reports.tenant_id` only, so the inspection side is invisible to it.

**Prescription:** one `tenants(id uuid primary key)` table, `reports.tenant_id` and `Inspection.tenantId` both FK to it, and either `reports` gains an FK to `Inspection` or the spec states explicitly that reports are tenant-owned and inspection-independent. Grounded in the rule that a value duplicated across tables with no FK spanning them will diverge — the only question is when.

**The cascade destroys the evidence for the spec's own gate.** Two cascades chain.

[VERIFIED] `lib/schema.prisma:11` — `  user      User       @relation(fields: [userId], references: [id], onDelete: Cascade)`
[VERIFIED] `lib/schema.prisma:20` — `  inspection Inspection @relation(fields: [inspectionId], references: [id], onDelete: Cascade)`

Scenario: a technician leaves and an admin runs `prisma.user.delete({ where: { id } })`, or an erasure request is honoured. One statement deletes that user's `Inspection` rows and, through the second cascade, every `AuditLog` row hanging off them. `AuditLog.action` is the only record in the system of who did what to an inspection — including, per spec §2, whether a verification checklist was completed before a report went to an insurer. The delete of the person who satisfied the gate destroys the proof they satisfied it, silently, with no error. [INFERENCE] on the trigger, [VERIFIED] on the two cascade declarations; this is the standard shape of audit loss I have seen where the audit table hangs off the entity rather than beside it.

Note also that `userId String` (`lib/schema.prisma:9`) is non-nullable, so `onDelete: SetNull` is not available without widening the column — the constraint pair has to be changed together or the change fails at delete time rather than at migrate time.

**Prescription:** `AuditLog` must not cascade — `onDelete: Restrict` on the inspection relation, with `inspectionId` retained as a plain non-FK id if you want inspections deletable, so audit rows outlive their subject. `Inspection`→`User` becomes `Restrict` plus a soft `deletedAt`, and every read path filters `deletedAt IS NULL`. Whichever way you go, write the answer into the schema: today "what happens to an inspection when its user is deleted" is answered only by a Prisma annotation nobody has read against the spec's retention needs.

**The distribution gate has no column to live in.** `reports` is `id, tenant_id, body jsonb, created_at` (`supabase/migrations/001_init.sql:1-6`). Spec §2 says a report may not be distributed unless its checklist is complete, but there is no `checklist_completed_at`, no `distributed_at`, no status. The invariant is therefore unrepresentable in the database: it can only be enforced by whichever code path happens to send the report, it cannot be enforced by a constraint, and after the fact nobody can tell from the row whether a distributed report was gated or not. **Prescription:** add `checklist_completed_at timestamptz` and `distributed_at timestamptz` with `CHECK (distributed_at IS NULL OR checklist_completed_at IS NOT NULL)`, so the gate is a property of the row rather than a property of one call site.

## 003 references a table that does not exist and was never applied

**The migration cannot succeed as written.**

[VERIFIED] `supabase/migrations/003_rls_fix.sql:6` — `  USING (tenant_id IN (SELECT tenant_id FROM public.user_tenant_access WHERE user_id = auth.uid()));`

`user_tenant_access` is created nowhere. `grep -rn "user_tenant_access"` over the whole fixture returns exactly one hit: the line above, the line that reads from it. Postgres resolves relations in a policy expression when the policy is created, not when it is evaluated, so `CREATE POLICY` here raises `relation "public.user_tenant_access" does not exist` and 003 aborts. [INFERENCE] on the parse-time resolution — [UNCONFIRMED] against this database; the exact check is `psql -c "CREATE POLICY t ON public.reports FOR SELECT USING (tenant_id IN (SELECT tenant_id FROM public.does_not_exist))"` on a scratch database, or `supabase db reset` against the local stack.

**What runs during the gap is the permissive policy.**

[VERIFIED] `supabase/APPLIED_LEDGER.txt:1-2` — the file contains exactly `001` and `002`; 003 is absent.
[VERIFIED] `supabase/migrations/002_policies.sql:4` — `  FOR SELECT USING (true);`
[VERIFIED] `supabase/migrations/002_policies.sql:6` — `GRANT SELECT, INSERT, UPDATE, DELETE ON public.reports TO anon, authenticated;`

So the deployed shape is 002: RLS enabled with a policy that admits every row, and full DML granted to `anon`. The gap between "003 is in the repo" and "003 is applied" is not a scheduling detail — it is the entire window in which spec §2's "Tenants must not read each other's reports" is false, and it has been open since 003 was written. Anyone reading the migrations directory concludes tenancy is fixed; the ledger says it is not; neither artifact is wrong on its own, which is why nobody noticed.

**003 is also not safely re-runnable.** It opens with `DROP POLICY IF EXISTS "Anon read access"` (line 2) and ends with `REVOKE ALL ON public.reports FROM anon` (line 8), with the failing `CREATE POLICY` between them. If the runner executes statement-by-statement rather than wrapping the file in one transaction, the drop lands, the create fails, and `reports` is left RLS-enabled with *no* SELECT policy — every authenticated read returns zero rows, which reads as data loss to a technician in the field. And `CREATE POLICY reports_tenant_select` has no idempotence guard, so a retry after any partial success fails with `duplicate_object` rather than converging.

**Prescription, grounded in the ordering rule that a migration may only reference objects an earlier applied migration created:** split this into `003_user_tenant_access.sql` (create the table, its PK, its FKs to `users` and `tenants`, and an index on `user_id`) and `004_rls_fix.sql` (the policy). Make the policy migration idempotent by adding `DROP POLICY IF EXISTS reports_tenant_select ON public.reports;` before the create. Require the runner to wrap each file in a single transaction so a failure leaves the pre-migration policy set intact rather than an empty one. Backfill `user_tenant_access` before the policy migration runs, in batches keyed by `user_id`, and confirm the row count matches the distinct `tenant_id` count in `reports` before cutting over — an empty access table plus a correct policy is a total read outage, and it looks identical to a working deploy on a dev database with one seeded user.
