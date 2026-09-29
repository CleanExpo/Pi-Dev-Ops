by: eng-data
categories:
  data_model: {state: PRESCRIBED, ref: "#data-model-ownership-and-report-gate-state", by: eng-data, blocking: true}
  migration:  {state: PRESCRIBED, ref: "#migration-003-cannot-apply-and-has-not-applied", by: eng-data, blocking: true}
cross_domain:
  - "002 grants SELECT to anon and its permissive policy is what is live in prod today — eng-authz owns whether reports are currently world-readable"
  - "003 is merged but unapplied and nothing in CI notices the ledger/directory disagreement — eng-release owns that drift; I answer `migration` from the schema side, so the chair should merge both rather than pick one"
  - "lib/sync-queue.ts:7 types Entry.status as `\"pending\" | \"failed\"` while line 50 counts `\"conflict\"`, so SYNC_CONFLICT is unreachable — eng-frontend owns the client store state machine"
  - "reports has no index on tenant_id even though every RLS-filtered read predicates on it — eng-performance owns the seq-scan cost"

## Data model ownership and report gate state

Three ownership decisions were made silently, and the one invariant the spec states outright has nowhere in the schema to live.

**The ownership table does not exist.** The only definition of who may see a tenant's rows is a subquery against a relation no migration creates. [VERIFIED] `supabase/migrations/003_rls_fix.sql:6`:

> `  USING (tenant_id IN (SELECT tenant_id FROM public.user_tenant_access WHERE user_id = auth.uid()));`

`grep -rn user_tenant_access` over the whole fixture returns that one line and nothing else. Ownership is therefore asserted by a predicate and defined by no table, no primary key, and no foreign key. [VERIFIED] `supabase/migrations/001_init.sql:3` creates the column it joins to as a bare scalar:

> `  tenant_id uuid NOT NULL,`

Nothing constrains that uuid to be a tenant that exists.

**The gate state has no column.** The spec's first gate is:

> A report may not be distributed unless its verification checklist is complete.

`reports` has exactly four columns — `id`, `tenant_id`, `body jsonb`, `created_at` [VERIFIED] `supabase/migrations/001_init.sql:1-6`. There is no `verified_at`, no `checklist_complete`, no `distributed_at`. So checklist completion is either an unvalidated key inside `body jsonb` or it lives only in application code, and "distributed" is not recorded at all. Concretely: a report is distributed to an insurer, the technician later edits `body` and clears a checklist item, and the database cannot tell you that a report went out unverified — there is no column that ever held the fact. This is exactly the decision the author did not notice was a decision.

**Two schemas describing two different universes, and the owner stored twice.** `lib/schema.prisma` declares `User`, `Inspection`, `AuditLog`; the SQL migrations declare `reports`. Neither knows the other exists. Inside Prisma, ownership is stored in two places at once — [VERIFIED] `lib/schema.prisma:9-11`:

> `  userId    String`
> `  tenantId  String`
> `  user      User       @relation(fields: [userId], references: [id], onDelete: Cascade)`

`userId` is a real relation; `tenantId` is a free string with no relation and no target table, so an inspection's tenant and its user's tenant can diverge and nothing enforces they agree.

**Deleting a user destroys the audit trail.** [VERIFIED] `lib/schema.prisma:20`:

> `  inspection   Inspection @relation(fields: [inspectionId], references: [id], onDelete: Cascade)`

combined with the `onDelete: Cascade` from `Inspection` to `User` above. Scenario: a technician leaves, an erasure request or an offboarding script deletes the `User` row; every `Inspection` cascades, every `AuditLog` cascades behind it. The audit records for reports already sent to insurers are gone, and no row anywhere records that they existed. [INFERENCE] I have watched this exact shape land twice — the audit table is always attached to the entity it audits, and always cascades with it, because `onDelete: Cascade` is the ORM's path of least resistance.

**Prescription** (grounded in the spec's own gates, not preference):

1. Create `user_tenant_access(user_id uuid, tenant_id uuid, primary key (user_id, tenant_id))` with real FKs to the users and tenants tables, in a migration that lands *before* any policy references it.
2. Add `tenants` and make `reports.tenant_id` and `Inspection.tenantId` FKs to it. Delete `Inspection.tenantId` entirely if the tenant is always derivable from `userId` — two copies of one fact with no constraint between them is the drift.
3. Add `verified_at timestamptz` and `distributed_at timestamptz` as real columns plus `CHECK (distributed_at IS NULL OR verified_at IS NOT NULL)`. Per METHOD #8, the spec's gate should be unable to be violated rather than merely checked in a handler.
4. Change the `AuditLog` FK to `ON DELETE RESTRICT` (or drop the FK and keep `inspection_id` as a plain column) so audit rows outlive their subject. If erasure genuinely requires removal, that is a redaction, and redaction is a different operation from cascade.

I would drop item 3 if someone shows me the gate is enforced by a constraint I have not opened. I could not find one; `grep -rn "checklist\|distribut"` hits only `spec.md`.

## Migration 003 cannot apply and has not applied

**It has not applied.** [VERIFIED] `supabase/APPLIED_LEDGER.txt` contains two lines:

> `001`
> `002`

while `supabase/migrations/` contains `001_init.sql`, `002_policies.sql`, `003_rls_fix.sql`. The database in front of users is at 002 — which means the live policy is the permissive one [VERIFIED] `supabase/migrations/002_policies.sql:4`:

> `  FOR SELECT USING (true);`

The spec's third gate, "Tenants must not read each other's reports", is unmet right now in the deployed schema, and the file that was supposed to fix it is sitting in the repo looking applied to anyone who reads the directory.

**It cannot apply as written.** [INFERENCE] Postgres resolves relations named in a policy's `USING` expression at `CREATE POLICY` time, not at first evaluation. `public.user_tenant_access` is created by no migration in this repo, so 003 aborts with `relation "public.user_tenant_access" does not exist`. Two outcomes, both bad, and which one you get depends on the runner:

- A runner wrapping each file in a transaction rolls the whole file back. The permissive policy survives and the ledger correctly stays at 002 — this is likely what already happened, and is the most probable explanation for the gap.
- A runner executing statement-by-statement without a wrapping transaction has already committed line 2, `DROP POLICY IF EXISTS "Anon read access"`, before line 4 fails. RLS is still enabled from 002 and there is now **no SELECT policy at all**, so every authenticated read of `reports` returns zero rows. The application does not error; it shows empty report lists. That is a total read outage that looks like "no data yet".

**Even after the table exists, the gap is a silent outage.** `user_tenant_access` is empty the moment it is created. Applying the policy against an empty membership table means `tenant_id IN (SELECT ...)` matches nothing for every user, so every read returns zero rows until a backfill lands. There is no backfill anywhere in this repo. The migration as designed swaps "everyone sees everything" for "nobody sees anything" and there is no third state in between.

**What runs during the gap is undefined.** During the window between dropping the permissive policy and seeding membership, in-flight report reads and any insurer distribution job reading `reports` see an empty table. Nothing in the repo pauses those.

**Prescription:**

1. Split 003. `003_tenant_access.sql`: create `user_tenant_access` with keys and FKs, then backfill it in the same file from the existing ownership source, batched by a stable key and written as an idempotent `INSERT ... ON CONFLICT DO NOTHING` so a partial failure re-runs to the same result.
2. Gate the policy swap on the backfill: `004_reports_policy.sql` asserts membership is non-empty for every distinct `tenant_id` present in `reports` (a `DO $$ ... RAISE EXCEPTION` guard) and only then drops the old policy and creates the new one, both inside one explicit transaction so the two-policy-states outcome above cannot occur.
3. Add the FK on `reports.tenant_id` as `NOT VALID` first and `VALIDATE CONSTRAINT` in a separate statement — the validating scan takes `SHARE UPDATE EXCLUSIVE`, not `ACCESS EXCLUSIVE`, and will not block writers on a table that has been accumulating reports.
4. `APPLIED_LEDGER.txt` is hand-maintained and disagrees with the directory. Per METHOD #6, this recurs, so the answer is a check, not a correction: CI compares the ledger against `migrations/*.sql` and fails the build on any disagreement. eng-release owns wiring that; I am naming the requirement.

[UNCONFIRMED] I cannot reach the database from here. To confirm the deployed state, a human should run against production:

```
psql "$DATABASE_URL" -c "select polname, polcmd, pg_get_expr(polqual, polrelid) from pg_policy p join pg_class c on c.oid = p.polrelid where c.relname = 'reports';"
psql "$DATABASE_URL" -c "select to_regclass('public.user_tenant_access');"
psql "$DATABASE_URL" -c "\d+ public.reports"
```

If the first returns the `USING (true)` policy and the second returns `NULL`, both findings above are confirmed rather than inferred, and the tenancy gate is open in production today.
