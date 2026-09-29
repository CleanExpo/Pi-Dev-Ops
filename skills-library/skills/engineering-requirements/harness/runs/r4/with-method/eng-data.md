by: eng-data
categories:
  data_model:  {state: PRESCRIBED, ref: "#ownership-is-unenforced-and-the-audit-trail-cascades-away", by: eng-data, blocking: true}
  migration:   {state: PRESCRIBED, ref: "#migration-003-cannot-apply-and-has-never-been-applied", by: eng-data, blocking: true}
  invariants:  {state: PRESCRIBED, ref: "#the-distribution-gate-has-no-representation-in-the-schema", by: eng-data, blocking: true}
cross_domain:
  - "002 grants INSERT/UPDATE/DELETE to anon and 003 adds only a SELECT policy — whether write paths are authorised at all is eng-authz's"
  - "eng-release also owns the ledger/directory disagreement; I claim migration here for the apply failure, not to overwrite that seat — chair should merge both"
  - "no down migration exists for 002 or 003, so reverting the RLS change is hand-written SQL — eng-rollback owns"
  - "lib/sync-queue.ts:48 counts status \"conflict\" but Entry.status is typed \"pending\" | \"failed\" (line 7), so SYNC_CONFLICT is unreachable — eng-concurrency owns the offline state machine"

## Ownership is unenforced and the audit trail cascades away

Three concrete defects, all in the "who owns the row" question.

**1. There is no tenant table and no foreign key on either tenant column.** `[VERIFIED]` `supabase/migrations/001_init.sql:3` — `  tenant_id uuid NOT NULL,` — is a bare uuid; nothing references a `tenants` table because no migration creates one. `[VERIFIED]` `lib/schema.prisma:10` — `  tenantId  String` — is a bare string on `Inspection` with no relation. The same logical tenant is therefore stored in two systems, in two types (`uuid` vs `String`), with nothing enforcing they agree. `[INFERENCE]` The concrete failure: a report is written with a `tenant_id` that exists in no tenancy record, and because 003's predicate is a subquery membership test rather than a join to a real key, that row is invisible to every authenticated user and visible to no one — an orphaned-but-billed row that surfaces only when a customer asks where their report went.

**2. Deleting a user destroys the audit trail.** `[VERIFIED]` `lib/schema.prisma:11` — `  user      User       @relation(fields: [userId], references: [id], onDelete: Cascade)` — and `[VERIFIED]` `lib/schema.prisma:20` — `  inspection   Inspection @relation(fields: [inspectionId], references: [id], onDelete: Cascade)`. That is a two-hop cascade: one `DELETE FROM users` removes every inspection and every `AuditLog` row attached to it. `[INFERENCE]` The scenario is a technician offboarding, or a GDPR erasure request — exactly the two moments when someone will later need the audit log to prove what was captured and when. An audit table that a routine user deletion silently empties is not an audit table. This is the answer to my seat's question — what happens to this row when its owner dies is written down in the schema, and what it says is "it disappears," which I do not believe anyone decided.

**3. `reports` has no index on the column RLS filters by.** `[VERIFIED]` `supabase/migrations/001_init.sql:1-6` declares only `id uuid PRIMARY KEY`; there is no `CREATE INDEX` in any of the three migrations. `[VERIFIED]` `003_rls_fix.sql:6` filters `USING (tenant_id IN (SELECT tenant_id FROM public.user_tenant_access WHERE user_id = auth.uid()))`. `[INFERENCE]` Every tenant-scoped read is then a sequential scan over the whole `reports` table plus a re-evaluated subquery per row — fine at 100 rows in dev, and the classic cost deferred to production once one large insurer's tenant is loaded.

**Prescription** (grounded in the constraint pair being the only enforcement that survives a bug in application code — method item 8, catch it where it cannot compile rather than where it pages someone):

- Create a `tenants` table and make both `reports.tenant_id` and `Inspection.tenantId` foreign keys to it. If Prisma and Supabase are genuinely separate databases, say so in the spec and state which one is authoritative for tenancy — right now the repo asserts neither.
- Change `AuditLog.inspection` to `onDelete: Restrict` and give `AuditLog` its own denormalised `tenantId` and `actorId` so it survives the deletion of what it describes. If erasure is a real requirement, it is a redaction `UPDATE` on the audit row, not a cascade.
- Add `CREATE INDEX CONCURRENTLY reports_tenant_id_idx ON public.reports (tenant_id);` — `CONCURRENTLY` because by the time anyone notices this, the table is large enough that the plain form takes a write lock.

**What would overturn this:** if `reports` is provably single-tenant-per-database, defect 1 and 3 both collapse. Nothing in the repo says that; if it is true, put it in `spec.md`.

## Migration 003 cannot apply and has never been applied

`[VERIFIED]` `supabase/migrations/003_rls_fix.sql:6` reads:

> `  USING (tenant_id IN (SELECT tenant_id FROM public.user_tenant_access WHERE user_id = auth.uid()));`

`[VERIFIED]` No migration creates `public.user_tenant_access`. `grep -rn "user_tenant_access"` over the fixture returns exactly one hit — that line. `[VERIFIED]` `supabase/migrations/001_init.sql` creates only `public.reports`.

`[VERIFIED]` `supabase/APPLIED_LEDGER.txt` contains two lines, `001` and `002`. 003 is not among them.

Two failures compound here, and the order matters.

**The migration is unrunnable as written.** `[INFERENCE]` Postgres resolves the table reference inside a policy `USING` expression at `CREATE POLICY` time, not at query time. So 003 aborts with `ERROR: relation "public.user_tenant_access" does not exist` the first time anyone runs it. It has never applied, and it cannot apply, in any environment. That is not a ledger bookkeeping gap — it is a migration that was merged in a state where success was impossible, which means it was never run even once against an empty database.

**Meanwhile production is running 002.** `[VERIFIED]` `supabase/migrations/002_policies.sql:3-4`:

> `CREATE POLICY "Anon read access" ON public.reports`
> `  FOR SELECT USING (true);`

and `[VERIFIED]` `002_policies.sql:6`:

> `GRANT SELECT, INSERT, UPDATE, DELETE ON public.reports TO anon, authenticated;`

`[INFERENCE]` The `DROP POLICY` and `REVOKE` in 003 are the only things that undo those two lines, and neither has run. The spec's gate — "Tenants must not read each other's reports" — is therefore currently false in every applied environment, and the file that was supposed to fix it is the reason nobody noticed: the fix exists in the repo, so a reader diffing migrations concludes the problem was solved. This is method item 4 exactly — a migration started and not finished leaves two truths with no rule for which wins, and here the losing truth is the one actually serving traffic.

**Prescription:**

1. Add `000_user_tenant_access.sql` (or fold it into 003) creating `public.user_tenant_access (user_id uuid NOT NULL, tenant_id uuid NOT NULL, PRIMARY KEY (user_id, tenant_id))` with a FK to `tenants`, RLS enabled, and an index on `user_id`. The policy subquery runs per row; without that index it is a seq scan inside a seq scan.
2. Backfill it before 003 runs. There is currently no source of truth for which user belongs to which tenant, so name one — until that source exists, applying 003 locks every authenticated user out of every report, which is a different outage, not a fix.
3. Ordering during the gap: 003 drops the permissive policy and creates the restrictive one in one transaction, so there is no window where reads are unprotected — but there *is* a window where reads return zero rows if the backfill has not completed. Backfill first, verify a non-zero row count, then apply 003.
4. `[UNCONFIRMED]` I cannot see the deployed database from here. Before anything else, run `psql -c "\d+ public.reports"` and `psql -c "SELECT polname, polcmd, pg_get_expr(polqual, polrelid) FROM pg_policy WHERE polrelid = 'public.reports'::regclass;"` against production and diff against these three files. My claim that 002's policy is live is inference from the ledger, not observation.

**What would overturn this:** a production `pg_policy` dump showing `reports_tenant_select` present. If it is present, the ledger is lying rather than the schema, which is a worse finding and belongs to eng-release.

## The distribution gate has no representation in the schema

`[VERIFIED]` `spec.md:8` states the product's hardest rule:

> `- A report may not be distributed unless its verification checklist is complete.`

`[VERIFIED]` `supabase/migrations/001_init.sql:1-6` is the entire `reports` table: `id`, `tenant_id`, `body jsonb`, `created_at`. There is no checklist column, no `verified_at`, no `distributed_at`, no status enum. `[VERIFIED]` No other table exists in any migration.

So the gate can only be enforced by whichever code path happens to call the distribution function, and the database will happily accept — and cannot even record — a distributed-but-unverified report. `[INFERENCE]` The failure is ordinary and will happen: a second caller (a retry, a cron re-send, an admin re-distribute button, a backfill script) reaches the send path without going through the one function that checks. Nothing in the row afterwards distinguishes a report that was verified from one that was not, so the incident is unanswerable — you cannot even query how many went out ungated.

Burying the checklist inside `body jsonb` is the version I expect to be proposed, and it is worse than a column: `jsonb` has no `NOT NULL`, no `CHECK`, no index by default, and no schema, so "complete" becomes a shape assertion made independently at every read site.

**Prescription** (grounded in the rule that a state transition a business gate depends on should be un-representable when illegal, not merely un-taken):

- Add explicit columns: `verification_state text NOT NULL DEFAULT 'incomplete'`, `verified_at timestamptz`, `distributed_at timestamptz`.
- Add the gate as a table constraint, so no code path can bypass it:
  `CHECK (distributed_at IS NULL OR verification_state = 'complete')`.
- Add it as `NOT VALID` first, then `VALIDATE CONSTRAINT` in a separate migration. On an existing `reports` table the one-step form takes `ACCESS EXCLUSIVE` for a full table scan; the two-step form takes it only briefly. Same reason `NOT NULL DEFAULT` is safe on PG 11+ but a retrofitted `NOT NULL` is not.
- The testable assertion for `test_oracle` (eng-test owns writing it): `SELECT count(*) FROM reports WHERE distributed_at IS NOT NULL AND verification_state <> 'complete'` must be 0, and an integration test must attempt that insert and expect a constraint violation — not expect the application to decline.

**What would overturn this:** if reports are distributed by a separate service holding its own state table, the constraint belongs there instead. Nothing in this repo shows such a table, and if it exists outside the repo, that is itself the finding.
