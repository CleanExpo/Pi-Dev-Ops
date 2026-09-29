by: eng-data
categories:
  data_model: {state: PRESCRIBED, ref: "#data-model", by: eng-data, blocking: true}
  migration:  {state: PRESCRIBED, ref: "#migration",  by: eng-data, blocking: true}
cross_domain:
  - "reports has no index on tenant_id, so every RLS-filtered read is a seq scan — eng-performance owns that"
  - "whether the 003 predicate is the right tenancy rule, and that 002's GRANT to anon is what is live today — eng-authz owns that"
  - "getSyncStatus counts a \"conflict\" status that the Entry type can never hold, so the branch is dead — eng-frontend owns the client state machine"

## Data model

**The gate the spec names first has no column to live in.** The spec states the distribution gate as a hard rule — `spec.md:8` `[VERIFIED]`:

> - A report may not be distributed unless its verification checklist is complete.

The only table that exists is `reports`, and its full column list is `id`, `tenant_id`, `body jsonb`, `created_at` — `supabase/migrations/001_init.sql:1-6` `[VERIFIED]`:

> `  body jsonb NOT NULL,`

There is no checklist state, no `checklist_complete`, no `distributed_at`, no `distributed_by`. Concretely: two API calls distribute the same report to the same insurer an hour apart and the row is byte-identical before and after — nothing in the database records that a distribution happened, so nothing can reject the second one and nothing can answer "was this report ever sent, and was the checklist complete at the moment it was sent?" during a dispute. Because the payload is untyped `jsonb`, a checklist stored inside `body` is also unconstrained: a report whose `body->'checklist'` key is absent, misspelled, or `null` is indistinguishable at the database level from one that passed. `[INFERENCE]` — this is the standard shape of "the invariant lives only in the handler", and it fails the first time a second code path (a retry, a cron re-send, a support script) writes the row without going through that handler.

**Prescription:** the gate needs to be representable and enforced in the schema, not only asserted in application code. Minimum: `checklist_complete boolean NOT NULL DEFAULT false` and `distributed_at timestamptz` on `reports`, plus a `CHECK (distributed_at IS NULL OR checklist_complete)`. That constraint makes "distributed with an incomplete checklist" unrepresentable rather than merely discouraged, and it is the assertion the test oracle can be written against.

**Ownership is stored twice and nothing makes the two agree.** `reports.tenant_id` is a bare `uuid NOT NULL` with no `REFERENCES` clause — `001_init.sql:3` `[VERIFIED]`:

> `  tenant_id uuid NOT NULL,`

Separately, `Inspection` carries its own tenant as an unrelated string — `lib/schema.prisma:10` `[VERIFIED]`:

> `  tenantId  String`

`grep -rn "tenant" .` over the whole fixture returns only these two declarations and the policy that reads them; there is no `tenants` table, no FK on either side, and no constraint spanning `Inspection.userId` and `Inspection.tenantId`. Concretely: a user is moved from tenant A to tenant B, the rows written before the move keep `tenant_id = A` and the rows after get `B`, and because no FK or trigger relates them, a single inspection can carry a `tenantId` its own `user` has no access to. Both values are writable independently by any caller with `INSERT`, so the divergence is a normal write, not a corruption.

**Prescription:** create the `tenants` table, make both `reports.tenant_id` and `Inspection.tenantId` real foreign keys to it, and decide explicitly whether tenant is derived from the user (in which case it should not be stored on the child at all) or assigned to the row at capture time (in which case a check must enforce that it matches the writer's tenant at write time). Storing it in both places with neither authoritative is the decision being made silently here.

**Deleting a user destroys the audit trail that proves what was reported.** The Prisma relations cascade twice — `lib/schema.prisma:11` and `:20` `[VERIFIED]`:

> `  user      User       @relation(fields: [userId], references: [id], onDelete: Cascade)`

> `  inspection Inspection @relation(fields: [inspectionId], references: [id], onDelete: Cascade)`

Concretely: a technician leaves and someone deletes their `User` row — a routine offboarding action, not an unusual one. Every `Inspection` they captured is deleted, and each of those cascades into every `AuditLog` row hanging off it. The audit log is the record of what was done to a report that was then distributed to an insurer; a single `DELETE FROM users WHERE id = ...` removes the evidence for reports that are still live in the insurer's hands. `[INFERENCE]` — a two-hop cascade into an append-only log table is the classic case where the cascade rule was chosen for the first hop (a user's inspections are theirs) and inherited by the second without anyone deciding it.

**Prescription:** audit rows must not be reachable by cascade. Either `onDelete: Restrict` on `AuditLog.inspection` with an explicit archival path, or soft-delete users (`deleted_at`) and never hard-delete a row with dependent audit history. Whichever is chosen, write the answer down in the schema — right now the retention rule for audit evidence exists only as an emergent consequence of two `Cascade` keywords.

## Migration

**Migration 003 cannot be applied as written, and no one has tried.** The applied ledger contains exactly two lines — `supabase/APPLIED_LEDGER.txt:1-2` `[VERIFIED]`:

> `001`
> `002`

But three migrations exist on disk (`find . -name "*.sql"` returns `001_init.sql`, `002_policies.sql`, `003_rls_fix.sql`). So the deployed database still carries the permissive policy from 002 — `002_policies.sql:3-4` `[VERIFIED]`:

> `CREATE POLICY "Anon read access" ON public.reports`
> `  FOR SELECT USING (true);`

That is the *third* spec gate ("Tenants must not read each other's reports") failing in the currently-deployed schema, while the repository reads as though it were fixed.

Worse, 003 will not apply when someone finally runs it. It selects from a table that no migration creates — `003_rls_fix.sql:6` `[VERIFIED]`:

> `  USING (tenant_id IN (SELECT tenant_id FROM public.user_tenant_access WHERE user_id = auth.uid()));`

`grep -rn "user_tenant_access" .` returns that single line and nothing else in the repository. Postgres resolves the relations named in a policy expression at `CREATE POLICY` time, so this statement raises `relation "public.user_tenant_access" does not exist` and aborts. `[UNCONFIRMED]` — confirm against the deployed database with `psql -c '\d public.user_tenant_access'` and `psql -c "SELECT policyname, qual FROM pg_policies WHERE tablename = 'reports'"`; if the table exists in production but in no migration file, that is dashboard-applied drift and the migration ledger is fiction rather than merely stale.

**The failure is ordered and destructive, not just a no-op.** `003_rls_fix.sql:2` and `:8` `[VERIFIED]`:

> `DROP POLICY IF EXISTS "Anon read access" ON public.reports;`

> `REVOKE ALL ON public.reports FROM anon;`

If this file is executed statement-by-statement rather than inside one transaction — which is how ad-hoc application through a SQL console works — the `DROP POLICY` succeeds, the `CREATE POLICY` fails on the missing table, and `reports` is left with RLS enabled and **zero** SELECT policies: every authenticated read returns zero rows. The technician app goes blank for all tenants simultaneously, and the operator's mental model is "I ran the security fix", so the blast radius reads as unrelated. There is no down file for 003 anywhere in `supabase/migrations/`, so the recovery step is hand-written under pressure.

**Prescription, in this order:**
1. Add the missing `user_tenant_access` table (or whatever the real membership table is) as `003a`, *before* the policy that reads it, with its own FKs to users and tenants.
2. Wrap 003 in `BEGIN; ... COMMIT;` so the `DROP`/`REVOKE` cannot survive a failed `CREATE POLICY`.
3. Ship a paired down file that restores a known-good SELECT policy, because the rollback from "no policy at all" is not obvious at 3am.
4. Reconcile the ledger against `pg_policies` and `information_schema.columns` before applying anything — the repository and the database currently disagree, and applying 003 on top of an unknown baseline is the mechanism by which a fix becomes an outage.

Note also that the Prisma models (`User`, `Inspection`, `AuditLog`) have no corresponding SQL migration at all — `find . -name "*.sql"` returns only the three `supabase/migrations` files, none of which create those tables. Two schema sources are diverging in the repository before either has met production. `[VERIFIED]`

I disagree in advance with any reading that treats the unapplied 003 as merely a pipeline-hygiene issue: the ledger gap is *why* the tenancy gate is open in the deployed schema, so it is a live data-exposure fact, not a process nit. `eng-release` owns whether the pipeline can detect the gap; I own that the schema it would apply is itself invalid.
