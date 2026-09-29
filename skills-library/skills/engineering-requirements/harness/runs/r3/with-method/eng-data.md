by: eng-data
categories:
  data_model: {state: PRESCRIBED, ref: "#data-model-two-schemas-no-owner-and-no-column-for-the-gate", by: eng-data, blocking: true}
  migration:  {state: PRESCRIBED, ref: "#migration-003-cannot-apply-and-the-ledger-does-not-know-it", by: eng-data, blocking: true}
cross_domain:
  - "whether the 003 predicate is the right tenancy rule at all, and what the live `USING (true)` policy has exposed since 002 — eng-authz owns that"
  - "`reports.tenant_id` has no index, so the RLS subquery scans on every SELECT — eng-performance owns the access path"
  - "the ledger says 002 and the directory says 003, and nothing in CI notices — eng-release owns the apply pipeline; eng-observability owns detecting the gap"
  - "`AuditLog` rows disappearing on a user delete is also a retention question if insurers or regulators expect the trail to outlive the account — eng-compliance owns that half"

## data model: two schemas, no owner, and no column for the gate

Three concrete problems, all in the same place.

**There are two disjoint data models and no rule for which is true.** The only table that exists in SQL is `reports` — `supabase/migrations/001_init.sql:1` `CREATE TABLE public.reports (` with columns `id`, `tenant_id`, `body jsonb`, `created_at` [VERIFIED]. The ORM knows nothing about it: `lib/schema.prisma` declares `model User`, `model Inspection`, `model AuditLog` and no `Report` [VERIFIED, `lib/schema.prisma:1` `model User {`, `:7` `model Inspection {`, `:15` `model AuditLog {`]. `grep -rn "CREATE TABLE"` over the repo returns exactly one hit [VERIFIED], so `Inspection` and `AuditLog` have no table and `reports` has no model. This is a migration someone started and did not finish (METHOD §4): the system now has two declarations of its shape and no rule for which wins. Decide which is authoritative and retire the other before either grows a third reader — a Prisma `db push` against this database will not find the tables it expects, and a hand-written query against `reports` will not find the ones Prisma expects.

**Ownership is asserted twice and enforced zero times.** `reports.tenant_id uuid NOT NULL` has no `REFERENCES` clause [VERIFIED, `001_init.sql:3` `tenant_id uuid NOT NULL,`], and `Inspection.tenantId String` has no relation either [VERIFIED, `lib/schema.prisma:10` `tenantId  String`]. `grep -rniE "create index|references"` finds no SQL foreign key anywhere in the repo [VERIFIED]. So the same logical tenant is stored on two rows in two stores, nothing spans them, and nothing stops an `Inspection` under tenant A producing a `report` row written with tenant B — a single transposed argument at the write site puts one tenant's report inside another tenant's RLS predicate, permanently, with no constraint that would ever surface it. Prescription: `tenant_id` is a real FK to a real `tenants` table in both models, and the write path derives the report's tenant from the inspection rather than accepting it as a parameter.

**The spec's first gate has nowhere to live.** The spec says:

> A report may not be distributed unless its verification checklist is complete.

`grep -rniE "checklist|verif|distribut"` over the whole repository matches only `spec.md` — no column, no enum, no state field [VERIFIED]. `reports` stores an opaque `body jsonb` and a timestamp; there is no `checklist_complete`, no `distributed_at`, no status. An invariant with no column is enforced by whichever application path happens to remember it, which is the same as unenforced. Prescription: `reports.checklist_completed_at timestamptz NULL` and `distributed_at timestamptz NULL`, plus `CHECK (distributed_at IS NULL OR checklist_completed_at IS NOT NULL)`. That is the cheapest form of METHOD §8 available in a database — the illegal state stops being reachable rather than being caught by a reviewer.

**Fourth, smaller, but a silent decision:** `AuditLog` cascades from `Inspection`, which cascades from `User` [VERIFIED, `lib/schema.prisma:20` `onDelete: Cascade)` and `:11` `onDelete: Cascade)`]. Deleting one user therefore hard-deletes their inspections and the audit record of what was done to them, in one statement, with no tombstone. Answering my seat's question — *if this row's owner is deleted, what happens to it* — the answer here is "the evidence goes too", and nobody wrote that down as a decision. An audit log that a subject can erase by deleting themselves is not an audit log. `onDelete: Restrict` on `AuditLog`, or a nullable `inspectionId` with `SetNull`, keeps the trail.

What would overturn all four: a second schema source of truth I have not been shown (a `prisma/migrations/` directory, a separate service owning `reports`). I looked — `find . -type f` shows eleven files and none of them is that [VERIFIED].

## migration: 003 cannot apply, and the ledger does not know it

`supabase/migrations/003_rls_fix.sql:6` reads:

> `USING (tenant_id IN (SELECT tenant_id FROM public.user_tenant_access WHERE user_id = auth.uid()));`

`grep -rn "user_tenant_access"` over the repository returns that one line and nothing else [VERIFIED] — no migration creates the table. Postgres resolves relation names in a policy expression at `CREATE POLICY` time, not at first evaluation, so this file aborts on execution with `relation "public.user_tenant_access" does not exist`. It has never run. `supabase/APPLIED_LEDGER.txt` contains exactly `001` and `002` [VERIFIED, `APPLIED_LEDGER.txt:1-2`], which is consistent with that — the ledger is not lying, it is recording a migration that failed or was never attempted, and nothing distinguishes those two cases.

The consequence is the gap, and the gap is the live state. Because 003 never applied, what is deployed is 002: `CREATE POLICY "Anon read access" ON public.reports FOR SELECT USING (true)` and `GRANT SELECT, INSERT, UPDATE, DELETE ON public.reports TO anon, authenticated` [VERIFIED, `002_policies.sql:3-4`, `:6`]. The spec's third gate — *"Tenants must not read each other's reports"* — is currently not merely unenforced but inverted, and the file everyone points at as the fix is the reason nobody has looked again. This is the exact drift my seat exists to catch, arriving from the opposite direction than usual: here the repository is ahead of the database rather than behind it, and the ledger is the only artifact that knows.

Prescriptions, in order:

1. **Split 003.** `003` creates `public.user_tenant_access (user_id uuid NOT NULL, tenant_id uuid NOT NULL, PRIMARY KEY (user_id, tenant_id))` with its own RLS, and backfills it from whatever currently determines tenancy. `004` then does the policy swap. A migration whose first statement depends on a table no migration creates is not a migration, it is a note.
2. **Make the swap atomic in the right order.** In one transaction: create the new policy, then `DROP POLICY IF EXISTS "Anon read access"`, then `REVOKE`. As written, 003 drops the permissive policy first (`:2`); if the `CREATE POLICY` then fails, `reports` is left RLS-enabled with no SELECT policy at all and every authenticated read returns zero rows — the fix's failure mode is a silent total outage of report reads, which reads to an operator as "the data is gone".
3. **Verify the backfill before the revoke.** Between creating `user_tenant_access` and revoking `anon`, assert `SELECT count(*) FROM reports r WHERE NOT EXISTS (SELECT 1 FROM user_tenant_access u WHERE u.tenant_id = r.tenant_id)` is zero. Non-zero means those reports become invisible to everyone the moment the policy lands, and you want that number before the cutover, not from a support ticket.
4. **Make "applied" a fact the database states, not a text file.** `APPLIED_LEDGER.txt` is a hand-maintained claim about a remote system, sitting in version control next to the thing it describes; per METHOD §6 the recurring correction here is not "someone forgot to add 003" but the absence of a check. The rule: CI diffs `supabase/migrations/*.sql` against `supabase_migrations.schema_migrations` on the target and fails on any file the target has not recorded. That check would have failed this repository on the commit that added 003.

`[UNCONFIRMED]` for the deployed state itself — I cannot reach the database from here. The command that settles it: `psql "$DATABASE_URL" -c "\d+ public.reports" -c "SELECT polname, pg_get_expr(polqual, polrelid) FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid WHERE c.relname='reports';" -c "SELECT version FROM supabase_migrations.schema_migrations ORDER BY 1;"` — one call returns the live policy set, the live grants and the real ledger, and the diff against these three files falls straight out of it. If that shows `reports_tenant_select` present, everything above about the gap is wrong and only the missing `user_tenant_access` migration file stands (as untracked drift in the other direction, which is eng-release's).
