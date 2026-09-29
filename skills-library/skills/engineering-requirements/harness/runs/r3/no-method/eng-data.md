by: eng-data
categories:
  data_model: {state: PRESCRIBED, ref: "#data-model", by: eng-data, blocking: true}
  invariants: {state: PRESCRIBED, ref: "#invariants", by: eng-data, blocking: true}
  migration:  {state: PRESCRIBED, ref: "#migration",  by: eng-data, blocking: true}
cross_domain:
  - "002 enables RLS with a SELECT-only policy, so the GRANT of INSERT/UPDATE/DELETE to authenticated is dead and every write must be arriving as service_role — eng-authz owns whether that is intended"
  - "the 003 predicate re-evaluates a subquery against an unindexed uuid column for every candidate row — eng-performance owns the plan"
  - "nothing compares APPLIED_LEDGER.txt against supabase_migrations.schema_migrations, so the drift below is invisible rather than merely present — eng-observability owns detection"
  - "003 ships with no down path; reverting it restores the anon-readable policy from 002 — eng-rollback owns the reversal sequence"

## Data model

Two schema sources describe two disjoint databases, and neither one owns a report.

`lib/schema.prisma` declares `User`, `Inspection`, `AuditLog` and no report table. `supabase/migrations/001_init.sql` declares `public.reports` and no inspection table. There is no migration that creates `inspections`, `users` or `audit_logs`, and no Prisma model for `reports` — confirmed by grep over the whole fixture: `CREATE TABLE` occurs exactly once, at `001_init.sql:1`. [VERIFIED] `supabase/migrations/001_init.sql:1` — `CREATE TABLE public.reports (`. So the object the spec is about ("the server generates a report that is distributed to insurers") lives in one store, and the capture records it is presumably generated from live in another, with no declared join and no shared key. Decide which store owns a report and whether Prisma or SQL is authoritative, before either grows a second writer.

Tenancy is a string in both stores and a foreign key in neither. [VERIFIED] `supabase/migrations/001_init.sql:3` — `  tenant_id uuid NOT NULL,`. [VERIFIED] `lib/schema.prisma:10` — `  tenantId  String`. There is no `tenants` table anywhere in the repo, so `reports.tenant_id` is an unconstrained uuid: a typo'd, stale, or attacker-supplied value inserts successfully and the row becomes permanently invisible to every tenant (the 003 predicate matches nothing) while still counting toward storage and any per-tenant total. This is the exact divergence shape in my seat file — the same logical owner stored in two places with no FK spanning both, so nothing enforces they agree. Prescription: create the `tenants` table, add `reports.tenant_id uuid NOT NULL REFERENCES public.tenants(id)`, and make `Inspection.tenantId` a real relation to the same table rather than a bare `String`.

Deleting a user destroys the audit trail. [VERIFIED] `lib/schema.prisma:11` — `  user      User       @relation(fields: [userId], references: [id], onDelete: Cascade)`, and [VERIFIED] `lib/schema.prisma:20` — `  inspection   Inspection @relation(fields: [inspectionId], references: [id], onDelete: Cascade)`. The cascade is transitive: one `DELETE FROM users WHERE id = ...` — an offboarded technician, a GDPR erasure, a test-account cleanup — removes that user's inspections and then every `AuditLog` row hanging off them. An audit log whose lifetime is bounded by the lifetime of its subject cannot answer "who did this and when" for anyone who has left, which is the only question audit logs exist to answer. [INFERENCE] I have watched this land as a data-loss incident twice: the cascade is written when the audit table is empty, and is discovered when someone asks for the history of a deleted account. Prescription: `AuditLog.inspectionId` becomes `onDelete: Restrict` (or nullable with `SetNull` plus a denormalised `actorEmail` snapshot), and user removal becomes a soft-delete or an anonymisation, not a row delete.

Note that the answer to my seat's standing question — if this row's owner is deleted, what happens to it — is currently *different in the two stores*: Prisma hard-cascades, `reports` has no owner FK at all so nothing happens and the row is orphaned. Neither behaviour is written in the spec.

## Invariants

The spec's primary gate has no column to live in. [VERIFIED] `spec.md:9` — `- A report may not be distributed unless its verification checklist is complete.` `public.reports` has exactly four columns — `id`, `tenant_id`, `body jsonb`, `created_at` — so there is no checklist state, no completeness flag, and no distribution timestamp anywhere in the schema. As written, "distributed" is an event that leaves no trace in the database, which means the gate can only be enforced in whatever application code happens to call the distribution path, and a second caller (a retry, a backfill, an admin re-send, the queue in `lib/sync-queue.ts` replaying a POST) bypasses it silently and undetectably. Burying the checklist inside `body jsonb` is not sufficient: jsonb is unconstrained, so a partial write produces a report that is *neither* complete nor incomplete.

Assertions to make true in the schema, each testable:

1. `SELECT count(*) FROM reports r LEFT JOIN tenants t ON t.id = r.tenant_id WHERE t.id IS NULL` is always `0`. Enforced by the FK prescribed above, not by a cron.
2. No row has `distributed_at IS NOT NULL AND checklist_complete = false`. Enforced by a table `CHECK (distributed_at IS NULL OR checklist_complete)` — a check constraint holds against every writer including psql, the dashboard, and a future worker; an `if` in a route handler holds against one.
3. `checklist_complete` is `NOT NULL DEFAULT false` from the moment the column is created, so a report is un-distributable until something positively marks it complete. Adding it nullable "for now" is the failure my seat exists to prevent: six months later half the rows are `NULL` and the gate has been open the whole time.
4. Distribution is at-most-once per report per recipient — needs a `report_distributions` table with a unique key, not a boolean, or the retry path re-sends to the insurer.

I expect eng-authz to also file under `invariants` for the tenant-isolation gate at `spec.md:11`; I am claiming the referential and gate-state half, not the policy predicate. Recorded here rather than overwritten.

## Migration

The tenant-isolation fix is in the repo and has never run, and it cannot run as written.

[VERIFIED] `supabase/APPLIED_LEDGER.txt:1-2` — the file's entire contents are `001` and `002`; there is no `003` line. [VERIFIED] `supabase/migrations/003_rls_fix.sql:1` — `-- Tenant-scoped replacement for the permissive policy in 002.` So the deployed database is still running 002, whose policy is [VERIFIED] `supabase/migrations/002_policies.sql:3-4` — `CREATE POLICY "Anon read access" ON public.reports` / `  FOR SELECT USING (true);` alongside [VERIFIED] `supabase/migrations/002_policies.sql:6` — `GRANT SELECT, INSERT, UPDATE, DELETE ON public.reports TO anon, authenticated;`. Every tenant's reports are readable by every tenant, and by anon, right now. The spec states the goal — [VERIFIED] `spec.md:14` — `- Migrations are applied and recorded.` — but states no mechanism, so this is a prescription, not a decision the spec made.

Applying 003 will fail. Its predicate reads a table that no migration creates: [VERIFIED] `supabase/migrations/003_rls_fix.sql:6` — `  USING (tenant_id IN (SELECT tenant_id FROM public.user_tenant_access WHERE user_id = auth.uid()));`. Grep across the fixture finds `user_tenant_access` at that one line and nowhere else. Two concrete outcomes, and which one you get depends on the runner, which nothing in the repo pins:

- **Run in one transaction** (`supabase db push`, `psql -1`): `CREATE POLICY` errors on the missing relation, the whole file rolls back, prod stays permissive, and the ledger stays at 002 — the current state, indefinitely, with an error someone may or may not read.
- **Run statement-by-statement** (SQL editor paste, `psql -f` without `-1`, a dashboard fix): `DROP POLICY IF EXISTS "Anon read access"` commits, `CREATE POLICY` fails, and `public.reports` is left with RLS enabled and **zero** SELECT policies. Every authenticated read returns zero rows. That is a total read outage on the product's primary table, produced by a migration whose stated purpose was to tighten a policy, and it is not obvious from the failure message that the DROP already committed.

Prescriptions, in order:

1. Add the missing `public.user_tenant_access` (or `tenants` + membership) DDL as `003a`, ordered before the policy, with its own PK and FKs. A policy that references a table is a dependency; the migration ledger must express it.
2. Make the file atomic and explicit — wrap it in `BEGIN; ... COMMIT;` so the statement-by-statement path cannot produce the half-applied state above, and pin the apply command in the repo so operators do not choose the runner ad hoc.
3. Make 001 re-runnable (`CREATE TABLE IF NOT EXISTS`) or accept that the ledger is the only thing preventing a re-run from erroring; today it is a two-line text file with no checksum, so a rebased or renumbered migration is undetectable.
4. Before believing any of the above, diff declared against deployed — the cheapest evidence in my seat, and the only thing that distinguishes "003 was never run" from "someone applied it by hand and the ledger is stale". [UNCONFIRMED] from here; run:
   - `select version from supabase_migrations.schema_migrations order by version;`
   - `select polname, polcmd, pg_get_expr(polqual, polrelid) from pg_policy p join pg_class c on c.oid = p.polrelid where c.relname = 'reports';`
   - `select to_regclass('public.user_tenant_access');`
   - `pg_dump --schema-only -t public.reports` diffed against `001_init.sql`.

If query 2 returns `Anon read access`, the isolation gate at `spec.md:11` is open in production and that is a live incident, not a pre-merge finding.
