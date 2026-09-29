by: eng-data
categories:
  data_model: {state: PRESCRIBED, ref: "#ownership-has-no-table", by: eng-data, blocking: true}
  migration:  {state: PRESCRIBED, ref: "#migration-003-cannot-apply", by: eng-data, blocking: true}
cross_domain:
  - "002 grants DELETE and UPDATE to `authenticated` and 003 revokes only from `anon`, so every logged-in user keeps write grants — eng-authz owns whether that is intended"
  - "the ledger lists 001 and 002 while the directory holds three files; I answer `migration` on the schema consequences only — eng-release owns the ledger/pipeline half and we overlap deliberately"
  - "003 has no down path, so the tenancy fix cannot be reversed once it does apply — eng-rollback owns that"
  - "nothing in the repo detects that the applied ledger and the migration directory disagree — eng-observability owns detection"
  - "`getSyncStatus` counts a `\"conflict\"` status that the `Entry` type cannot hold, so `SYNC_CONFLICT` is unreachable — eng-concurrency owns the queue state machine"

## Ownership has no table

**The tenancy model rests on a relation that is not declared anywhere.** Migration 003 scopes reads by joining `user_tenant_access` — `[VERIFIED] supabase/migrations/003_rls_fix.sql:6`:

> `  USING (tenant_id IN (SELECT tenant_id FROM public.user_tenant_access WHERE user_id = auth.uid()));`

`[VERIFIED]` a repo-wide grep for `user_tenant_access` returns exactly that one line — no `CREATE TABLE`, no seed, no Prisma model. The same is true of any `tenants` table. So `reports.tenant_id` (`[VERIFIED] supabase/migrations/001_init.sql:3`: `  tenant_id uuid NOT NULL,`) is an unconstrained uuid pointing at nothing: no foreign key, no referent, nothing that fails when a report is written with a tenant id that has never existed. A typo'd or stale tenant id inserts cleanly today and becomes permanently invisible to every reader tomorrow, and no query in the repo would surface it.

**Prescription (grounded in the spec gate "Tenants must not read each other's reports"):** declare `tenants(id uuid primary key)` and `user_tenant_access(user_id uuid, tenant_id uuid references tenants(id), primary key (user_id, tenant_id))` in a migration that precedes 003, and add `reports.tenant_id references tenants(id)`. Until a foreign key spans them, "which tenant owns this row" is enforced by whichever code path wrote it.

**Two declared schemas describe two different databases.** `lib/schema.prisma` models `User`, `Inspection`, `AuditLog` and never mentions `reports`; the SQL migrations create `reports` and never mention inspections or audit logs. Neither is a subset of the other, so there is no single answer to "what is the schema". `Inspection` carries its own tenancy string with no relation attached — `[VERIFIED] lib/schema.prisma:10`:

> `  tenantId  String`

That is the divergence case in its classic form: the same logical owner is stored on `reports.tenant_id` and `Inspection.tenantId`, in two schema languages, with nothing enforcing that they agree. **Prescription:** name one authoritative source. If Prisma owns the app tables, its models must be generated into the same `supabase/migrations` ledger the RLS policies live in; if SQL owns them, `schema.prisma` must be regenerated from the database and checked. Two ledgers is not a schema, it is a diff waiting to be discovered in an incident.

**Deleting a user destroys the audit trail.** `[VERIFIED] lib/schema.prisma:11` and `:20`:

> `  user      User       @relation(fields: [userId], references: [id], onDelete: Cascade)`

> `  inspection   Inspection @relation(fields: [inspectionId], references: [id], onDelete: Cascade)`

`[INFERENCE]` The two cascades chain: one `DELETE FROM "User"` removes every `Inspection` that user captured and every `AuditLog` attached to those inspections, in one statement, with no tombstone. This is the mechanism behind every "we cannot reconstruct who changed the report" postmortem I have sat in — the audit rows are deleted by the very event they exist to explain, and a technician offboarding is enough to trigger it. Nothing in the spec says an audit log may be deleted; the cascade decided it silently. **Prescription:** `AuditLog.inspection` becomes `onDelete: Restrict` (or the FK is dropped and `inspectionId` retained as a denormalised value), and user removal is a soft delete. Note the second half of the trap: if you move to soft delete without changing these cascades, the cascades simply stop firing and you get orphaned-but-visible inspections instead. Pick one and write it in the schema, not in application code.

**The distribution gate has no column to stand on.** `[VERIFIED] spec.md:8`:

> `- A report may not be distributed unless its verification checklist is complete.`

`reports` has four columns — `id`, `tenant_id`, `body jsonb`, `created_at`. There is no checklist state, no `verified_at`, no distribution status, so the gate can only be evaluated by reading untyped keys out of `body` and nothing prevents a row being distributed twice or distributed with an empty checklist. **Prescription:** model the gate as columns (`checklist_complete boolean NOT NULL DEFAULT false`, `distributed_at timestamptz`) with a `CHECK (distributed_at IS NULL OR checklist_complete)`. A gate that exists only in the caller is a gate that the next caller does not have.

## Migration 003 cannot apply

**It is not merely un-applied; it will error when someone runs it.** `[VERIFIED] supabase/APPLIED_LEDGER.txt` contains exactly:

> `001`
> `002`

while `supabase/migrations/` holds `001_init.sql`, `002_policies.sql`, `003_rls_fix.sql`. `[INFERENCE]` Postgres analyses a policy's `USING` expression at `CREATE POLICY` time, so with no `public.user_tenant_access` relation the statement fails with `relation "public.user_tenant_access" does not exist` and the file aborts. The reason 003 is not in the ledger may well be that it has already been attempted and failed. `[UNCONFIRMED]` — confirm with `psql "$DATABASE_URL" -c '\d public.user_tenant_access'` (expect `Did not find any relation`) and `psql "$DATABASE_URL" -c "select policyname, qual from pg_policies where tablename='reports'"`.

**What runs during the gap is the permissive policy.** Because 003 never landed, the deployed shape is 002's — `[VERIFIED] supabase/migrations/002_policies.sql:3-6`:

> `CREATE POLICY "Anon read access" ON public.reports`
> `  FOR SELECT USING (true);`

> `GRANT SELECT, INSERT, UPDATE, DELETE ON public.reports TO anon, authenticated;`

So right now the migration files claim tenant isolation and the database serves every report to every caller including `anon`. Anyone reading the repo to answer "are tenants isolated?" gets the wrong answer from the source of truth they would naturally reach for. That drift — files and ledger agreeing with each other and both disagreeing with the database — is the specific thing I would page someone over, and it is why this category is blocking.

**Prescription (ordering, grounded in the dependency above):**

1. New migration `003_tenancy_tables.sql` creating `tenants` and `user_tenant_access` and the FK from `reports.tenant_id`, before any policy references them. Renumber the RLS fix to `004`.
2. A backfill for `user_tenant_access`. **This has no source today** — no existing table maps a user to a tenant, so the mapping has to come from outside the database and must be resolved before step 3, or every authenticated user reads zero reports the moment the policy lands. That is the failure mode of applying the fix correctly: it is a silent, total read outage for real users, and the health endpoint would report `"status": "ok"` throughout.
3. Adding the FK on `reports.tenant_id` takes `ACCESS EXCLUSIVE` briefly and then validates the whole table. On anything past a few hundred thousand rows do it as `ADD CONSTRAINT ... NOT VALID` followed by a separate `VALIDATE CONSTRAINT`, which takes only `SHARE UPDATE EXCLUSIVE`. `[INFERENCE]` — this passes instantly on an empty dev table and is the exact shape that holds a write lock on a hot table in production.
4. Any backfill written for step 2 must be batched by primary key and idempotent (`ON CONFLICT DO NOTHING` on the composite key), so a partial failure can be re-run to the same end state. There is no backfill script in the repo to review; this is a requirement on the one that gets written.
5. Before merge, prove the drift is closed rather than assuming it: `pg_dump --schema-only "$DATABASE_URL"` diffed against the concatenated migration files. Both the missing table and the missing constraints fall out of that one diff.
