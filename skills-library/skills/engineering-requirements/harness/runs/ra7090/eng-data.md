by: eng-data
contributed: [eng-data]
categories:
  data_model: {state: PRESCRIBED, ref: "#restrict-fk-under-a-shared-cascade-ancestor", by: eng-data, blocking: true}
  migration:  {state: PRESCRIBED, ref: "#unindexed-fk-non-concurrent-unique-index-and-an-owner-gate-the-build-script-does-not-honour", by: eng-data, blocking: true}
  invariants: {state: PRESCRIBED, ref: "#null-sourcephotoid-carries-two-incompatible-meanings-in-a-legal-export", by: eng-data, blocking: true}
cross_domain:
  - "these two migrations are the only 2 of 205 with a down.sql, and `prisma migrate deploy` never reads down.sql — the documented rollback is a comment, not an executable path. eng-release owns whether rollback is real."
  - "the contract test at lib/__tests__/ra7090-original-asset-linkage-contract.test.ts asserts the TEXT of migration.sql, not the behaviour of a database; `pnpm test:db` already stands up a real pg16, so a behavioural test is available and unused. The QA/test seat owns the oracle."
  - "POST /api/account/delete deliberately preserves Invoice/Report/Estimate/CreditNote/InvoicePayment against the retention promise, but lets Inspection→InspectionPhoto/EvidenceItem cascade to destruction; spec.md §C-8 names photographs as a retention-matrix category. eng-privacy/retention owns that contradiction."

## RESTRICT FK under a shared cascade ancestor

The new constraint is not a leaf. It creates a sideways dependency between two branches of an existing cascade, and nothing in the migration or its tests exercises the parent delete.

The three edges, all verified:

- `prisma/schema.prisma:5558` — `sourcePhoto         InspectionPhoto? @relation("EvidenceSourcePhoto", fields: [sourcePhotoId], references: [id], onDelete: Restrict)`
- `prisma/schema.prisma:5499` — `  inspection   Inspection @relation(fields: [inspectionId], references: [id], onDelete: Cascade)` (on `EvidenceItem`)
- `prisma/schema.prisma:3298` — `  inspection   Inspection @relation(fields: [inspectionId], references: [id], onDelete: Cascade)` (on `InspectionPhoto`)

So one `DELETE FROM "Inspection"` fans out to *both* `InspectionPhoto` and `EvidenceItem`, and the RESTRICT check sits between them. `Inspection` in turn cascades from `User` (`prisma/schema.prisma:2044` — `  user   User   @relation(fields: [userId], references: [id], onDelete: Cascade)`), so account deletion is the same statement one level up. [VERIFIED]

Both callers are live, not hypothetical:

- `app/api/inspections/[id]/route.ts:580` — `    await prisma.inspection.delete({` [VERIFIED]
- `app/api/account/delete/route.ts:169` — `        await tx.user.delete({ where: { id: user.id } });` [VERIFIED]

The scenario: a technician uploads a photo, mints evidence from it (`sourcePhotoId` set at `app/api/inspections/[id]/evidence/route.ts:432`), the office later deletes the inspection or the owner deletes their account. Postgres cascades to `InspectionPhoto`; `RI_FKey_restrict_del` for `EvidenceItem_sourcePhotoId_fkey` is non-deferrable and fires at that row's delete. If the `EvidenceItem` cascade branch has not already run, the statement aborts with `violates foreign key constraint "EvidenceItem_sourcePhotoId_fkey"` and both endpoints return a 500 through `fromException` with no actionable message. `NO ACTION` would survive this — the check reaches end-of-statement, by which time the sibling cascade has removed the referencing rows. [INFERENCE] — mechanism is Postgres's documented RESTRICT/NO ACTION deferral difference; I have watched this exact shape break tenant purges.

**The part that makes this blocking is not that it fails — it is that whether it fails is not determined by anything in this repo.** Which branch runs first is the firing order of two `RI_ConstraintTrigger_a_<oid>` triggers on `Inspection`, ordered lexicographically by OID string. That order was fixed by whenever those two constraints happened to be created, differs between production's historical migration replay and any freshly-built database, and is not expressible in `schema.prisma`. "It worked in CI" and "it works in prod" are independent coin flips.

The soft-delete path makes it permanent rather than transient: `DELETE /api/inspections/[id]/evidence` tombstones to `REJECTED` rather than deleting (`app/api/inspections/[id]/evidence/route.ts:566` — `        data: { status: "REJECTED" },` [VERIFIED]). A retired evidence item still holds its `sourcePhotoId`, so there is no user-reachable action that releases the pin. Once an inspection has ever had photo-backed evidence, it can never be deleted again.

Prescribe, in order of preference:

1. Change the referential action to `NO ACTION` (`onDelete: NoAction` in Prisma). It still refuses a bare `DELETE FROM "InspectionPhoto"` — the custody guarantee the migration comment argues for is fully preserved — and it stops the cascade from tripping over itself. This is a one-word change and I believe it is the right answer.
2. Whichever action you land on, add a DB-backed test that deletes an `Inspection` carrying a photo-backed `EvidenceItem` and asserts the chosen outcome. `pnpm test:db` (`scripts/ci/test-with-db.sh`) already stands up `pgvector/pgvector:pg16` and runs `prisma migrate deploy`, so this costs one file. The existing test file asserts the string `ON DELETE RESTRICT` appears in the SQL; it cannot observe the interaction at all.
3. Decide explicitly what *should* happen to a claim's evidence when its inspection or its owner's account is deleted, and write that decision into `docs/architecture/RESTOREASSIST-DECISIONS.md`. Right now the answer is "an FK violation decides", which is nobody's intent. Per the method (#11), this belongs written down, not remembered.

Falsifier: if you run the delete against a database built by replaying all 205 migrations in order and it succeeds, my ordering claim is wrong for that build — but the OID-order dependence remains, so the test in (2) is still the thing that holds it.

## Unindexed FK, non-concurrent unique index, and an "owner gate" the build script does not honour

Three costs deferred to the first production deploy, all in the same pair of migrations.

**No index on the referencing column.** `EvidenceItem`'s index list is `inspectionId`, `evidenceClass`, `capturedById`, `capturedAt`, `workflowStepId`, `[inspectionId, evidenceClass]`, `[inspectionId, status]` (`prisma/schema.prisma:5573-5579`); `grep -rn "sourcePhotoId" prisma/ | grep -i index` returns nothing. [VERIFIED] Postgres does not auto-index the referencing side of a foreign key. Every delete of an `InspectionPhoto` row now runs `SELECT 1 FROM "EvidenceItem" WHERE "sourcePhotoId" = $1 FOR KEY SHARE` as a sequential scan of the whole table — *once per photo row*. A single inspection commonly carries a hundred-plus photos, so one inspection delete becomes a hundred-plus full scans of `EvidenceItem` inside one transaction holding row locks against live field uploads. Add `@@index([sourcePhotoId])`.

**Non-concurrent unique index build.** `prisma/migrations/20260725000000_ra7090_evidence_capture_replay_key/migration.sql:10` — `CREATE UNIQUE INDEX "EvidenceItem_captureReplayKey_key" ON "EvidenceItem"("captureReplayKey");` [VERIFIED] This takes `SHARE` on `EvidenceItem` for the duration of a full heap scan, blocking every `INSERT` — i.e. every technician uploading evidence in the field — for that window. The column is all-NULL so the index is empty, but the *scan* is not free and scales with the table. The repo already knows this: four migrations use `CONCURRENTLY` (`20260407_n1_performance_indexes`, `20260407_perf_composite_indexes`, `20260516000000_inspection_close_terminal_state`, `20260516010000_inspection_close_terminal_index`) and `scripts/ci/test-with-db.sh` has a documented `migrate resolve --applied` workaround for them. [VERIFIED] The convention exists and this migration does not use it.

**The owner gate is imaginary.** Both migration headers say execution is owner-gated — `-- Forward-only; execution is owner-gated (Rule 29).` — and the session handoff repeats it (`docs/session-handoffs/handoff-20260725T002401Z.md:78` — `NOT executed — Rule 29 owner-gated`). But the production build applies migrations unattended: `scripts/build.sh:48` — `      pnpm exec prisma migrate deploy` [VERIFIED], reached on any `VERCEL_ENV` that is not `preview`/`development`. The moment this branch merges and a production build runs, both migrations execute during the build, in whatever window Vercel picks, with no human present. There is no `lock_timeout` or `statement_timeout` anywhere in `prisma/migrations` or `scripts` (`grep -rln "lock_timeout\|statement_timeout"` returns nothing) [VERIFIED], so a blocked DDL waits behind a long transaction and queues every subsequent write behind it.

Prescribe:

- Add `@@index([sourcePhotoId])` to `EvidenceItem` and a matching `CREATE INDEX CONCURRENTLY` migration before the FK is allowed to reach production.
- Take the row-count first. `spec.md §40` demands exactly this discipline for schema change ("prod row-count audit of every dead store ... before any drop — 'zero writers in code' is not 'zero rows in prod'"); it applies with equal force to an index build. Run `SELECT count(*) FROM "EvidenceItem"; SELECT count(*) FROM "InspectionPhoto";` against production and record the numbers in the migration header. [UNCONFIRMED] — I cannot reach the production database from here.
- Set `SET lock_timeout = '3s';` at the top of any migration that takes a table-level lock, so a blocked DDL fails the deploy instead of queueing production writes behind itself. Per the method (#6), this is a rule for the migration template, not a note on this PR.
- Either wire a real gate (`RA_ALLOW_MIGRATE=1` guard in `scripts/build.sh`) or delete the "owner-gated" claim from the headers. A gate that only exists in a comment is worse than no gate, because the next reader trusts it.

Credit where due: `scripts/build.sh` already fails closed on the `:6543` pooler and runs `scripts/check-schema-drift.mjs` after deploy. The drift vector my seat normally has to hunt for is already instrumented here.

## NULL sourcePhotoId carries two incompatible meanings in a legal export

State this as the assertion: **no evidence custody export may present a non-null `originalSha256` alongside a null `originalStoragePath` without saying which of the two reasons applies.**

The write path enforces this for new rows and fails closed — `app/api/inspections/[id]/evidence/route.ts:246`:

```
        if (originalPhotoId && !storedPhoto?.originalStoragePath) {
```

with the message `"Referenced photo has no retrievable original asset — re-upload it via the photo endpoint before creating evidence from it."` [VERIFIED] The code comment at line 241 names the principle exactly: "a hash with no retrievable original behind it is a claim nothing can ever satisfy."

Every row that predates the migration violates that principle and is exempted, because the columns are added nullable with no backfill and no marker. The export emits them raw — `lib/evidence/manifest-export.ts:297-298`:

```
    sourcePhotoId: evidence.sourcePhotoId,
    originalStoragePath: evidence.originalStoragePath,
```

[VERIFIED] alongside `originalSha256: evidence.hashSha256` on line 294. A legacy row therefore exports a populated SHA-256 next to `"originalStoragePath": null`, and a reader — insurer, adjuster, or opposing counsel in the dispute pack this feeds (`lib/dispute-pack.ts:634-635`) — has no way to distinguish "this platform did not record original-asset linkage when this evidence was captured" from "this evidence has no original and the hash refers to nothing." The second reading is the damaging one, and it is the natural one, because the field is present and null rather than absent.

This is created by this change: before it, the field did not exist and no claim was made. Adding an always-null field to a legal artefact is an assertion, not an omission.

Prescribe:

- Emit a tri-state rather than a bare null: `originalAssetLinkage: "BOUND" | "NOT_RECORDED" | "ABSENT"`, where `NOT_RECORDED` is stamped for any evidence row whose `createdAt` predates the migration's deploy timestamp. That timestamp is a constant you know at deploy time; it does not need a backfill.
- Count the affected population before deciding whether a backfill is worth it: `SELECT count(*) FROM "EvidenceItem" WHERE "hashSha256" IS NOT NULL AND "sourcePhotoId" IS NULL;` and the subset recoverable from the audit log, `SELECT count(*) FROM "AuditLog" WHERE "entityType" = 'InspectionPhoto' AND changes::jsonb ? 'storagePath';` — the photo route writes `storagePath` into that blob (`app/api/inspections/[id]/photos/route.ts:397`, `              storagePath: uploadResult.storagePath,` [VERIFIED]), so some linkages are reconstructible. The successor migration's own `down.sql` says the opposite — "the original storage path for a photo whose audit-log entry has aged out exists nowhere else" — which is a claim about audit-log retention nobody has checked. [UNCONFIRMED] — needs the two counts above plus the audit-log retention policy.
- If a backfill happens, it must be batched by `id` cursor and idempotent (`WHERE "sourcePhotoId" IS NULL` is already the batching predicate). Do not write it as one `UPDATE "EvidenceItem" SET ...` over the table.

Where my instinct and the method disagree: my domain reflex is to demand the backfill before the columns ship. The method (#1, boring version first) wins — the deploy-timestamp tri-state is the boring version, it removes the ambiguity completely, and it costs no table rewrite. Backfill only if the counts above say it buys something.
