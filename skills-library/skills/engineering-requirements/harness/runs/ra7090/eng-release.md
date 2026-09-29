by: eng-release
contributed: [eng-release]
categories:
  failure_modes:  {state: PRESCRIBED, ref: "#fk-restrict-collides-with-the-inspection-cascade", by: eng-release, blocking: true}
  observability:  {state: PRESCRIBED, ref: "#the-drift-gate-cannot-fail-on-either-object-this-change-adds", by: eng-release, blocking: true}
  test_oracle:    {state: PRESCRIBED, ref: "#no-observation-of-the-live-system-proves-this-shipped", by: eng-release}
cross_domain:
  - "spec.md §8 makes EvidenceItem→InspectionPhoto an FK and §34 makes evidence immutable, but Inspection still cascade-deletes both — the ownership rule for 'what happens to children when the parent dies' is contradictory at the data-model level; eng-data owns that"
  - "down.sql exists for these two migrations and for none of the other 205; Prisma has no down runner and nothing in scripts/, .github/ or package.json executes it, so the documented rollback is an unrehearsed manual psql action — eng-ops/the chair owns whether that is acceptable"
  - "DELETE /api/inspections/[id] and /api/inspections/bulk-delete scope by `userId`, not organisationId, while the spec says 'All access is organisation-isolated' — eng-authz owns that"

## FK RESTRICT collides with the Inspection cascade

`20260725010000_ra7090_original_asset_linkage` adds a `RESTRICT` foreign key from `EvidenceItem.sourcePhotoId` to `InspectionPhoto.id`. Both of those tables already cascade-delete from `Inspection`.

[VERIFIED] `prisma/migrations/20260725010000_ra7090_original_asset_linkage/migration.sql:29` — `ALTER TABLE "EvidenceItem" ADD CONSTRAINT "EvidenceItem_sourcePhotoId_fkey" FOREIGN KEY ("sourcePhotoId") REFERENCES "InspectionPhoto"("id") ON DELETE RESTRICT ON UPDATE CASCADE;`

[VERIFIED] `prisma/schema.prisma:3298` (InspectionPhoto) — `inspection   Inspection @relation(fields: [inspectionId], references: [id], onDelete: Cascade)`

[VERIFIED] `prisma/schema.prisma:5499` (EvidenceItem) — `inspection   Inspection @relation(fields: [inspectionId], references: [id], onDelete: Cascade)`

The concrete scenario: a technician captures a device-signed photo on inspection X, so an `EvidenceItem` row exists with `sourcePhotoId` pointing at an `InspectionPhoto` of X. A manager then deletes inspection X.

[VERIFIED] `app/api/inspections/[id]/route.ts:580` — `await prisma.inspection.delete({`
[VERIFIED] `app/api/inspections/bulk-delete/route.ts:41` — `const deleted = await prisma.inspection.deleteMany({`

Postgres cascades the `Inspection` delete to both referencing tables. `ON DELETE RESTRICT` is checked immediately and, unlike `NO ACTION`, cannot be deferred to end-of-statement — so if the `InspectionPhoto` rows are processed before the `EvidenceItem` rows in that cascade (the order is by constraint OID, not by anything the author controls), the statement aborts with a foreign-key violation on a table the caller never named. `fromException` turns it into a 500. Deletion of any inspection carrying signed evidence becomes intermittently or permanently impossible, and `bulk-delete` fails the whole batch, not the one offending row. [INFERENCE] — this is the standard RESTRICT-inside-cascade footgun; I have seen it land as "delete worked in staging and 500s in prod" because staging had no evidence rows to trip it.

The justification recorded for the choice checked the wrong thing:

[VERIFIED] `docs/session-handoffs/handoff-20260725T002401Z.md:19` — `no production code path deletes `InspectionPhoto` rows (grep-verified), so nothing existing breaks`

That grep is true and insufficient. Nothing deletes `InspectionPhoto` *directly*; the schema deletes it *transitively* on every inspection delete. This is my seat's canonical bite — old code writing against a constraint that just tightened — and the pipeline applies the tightening automatically: `scripts/build.sh:48` runs `pnpm exec prisma migrate deploy` on every production build with no approval step, so merging this branch is the deploy.

**Prescription.** Decide explicitly what happens to evidence when its parent inspection dies, and make the DB enforce that decision rather than discover it. Either (a) change the FK to `ON DELETE NO ACTION` so the check defers and the cascade can remove the referencing `EvidenceItem` rows in the same statement, or (b) keep `RESTRICT` and make it a real product rule — remove the `Cascade` from `EvidenceItem.inspection` and `InspectionPhoto.inspection`, and have the delete routes refuse an inspection that holds custody material with a 409 naming the blocking evidence. (b) is more consistent with §34 ("no mutable field masquerades as an audit trail") but is a behaviour change requiring a §44 spec update. Whichever is chosen, the acceptance test is a delete of an inspection that has one device-signed evidence row, asserted against a real Postgres — not a mocked Prisma client, which will not reproduce cascade ordering.

**What would overturn this finding:** a test run of `DELETE /api/inspections/[id]` against a Postgres instance with both migrations applied and one `EvidenceItem.sourcePhotoId` populated, returning 200. If that passes, I am wrong about the ordering and this drops to a `NO ACTION` style nit.

## The drift gate cannot fail on either object this change adds

This change's two behavioural guarantees are enforced by exactly two database objects: the unique index `EvidenceItem_captureReplayKey_key` (exactly-once offline replay) and the FK above (custody). The build's own drift gate will not fail on either.

[VERIFIED] `scripts/check-schema-drift.mjs:28` — ` * Limits: relations and CHECK constraints are still not compared (enums now are,` — the FK is compared by nothing at all.

[VERIFIED] `scripts/check-schema-drift.mjs:419-420` —
```js
  const strict = process.env.DRIFT_STRICT === "1";
  const fatal = columnDrift.length > 0 || strict;
```
[VERIFIED] `scripts/check-schema-drift.mjs:446` — `"[drift-check] unique/nullability drift is REPORT-ONLY (set DRIFT_STRICT=1 to enforce) — not failing the build.",`

[VERIFIED] A grep for `DRIFT_STRICT` across the repo returns only `scripts/check-schema-drift.mjs` and one line of `docs/audits/ra-founder-remediation-queue.md`. It is set in no shell script, no workflow, and no Vercel config. The build therefore always runs in report-only mode for unique indexes.

Why that matters here specifically. The route's exactly-once guarantee is a read-then-create with no lock; only the unique index closes the window:

[VERIFIED] `app/api/inspections/[id]/evidence/route.ts:374-375` — `// exactly-once guarantee itself is the unique \`captureReplayKey\`` / `// persisted on the evidence row, which never expires.`
[VERIFIED] `app/api/inspections/[id]/evidence/route.ts:472` — `if ((err as { code?: string } | null)?.code === "P2002") {`

The scenario: `CREATE UNIQUE INDEX "EvidenceItem_captureReplayKey_key"` no-ops against the `:6543` transaction pooler — the exact failure this repo was burned by and documents at `scripts/build.sh:6-10` — or the index is dropped by a later operator action. The `captureReplayKey` *column* is present, so the fatal column comparator stays quiet; the unique comparator fires and prints a warning; `check-schema-drift.mjs` exits 0; the build ships. A field device that queues one signed capture and replays it twice concurrently on reconnect now creates two `EvidenceItem` rows and two `CustodyEvent` rows for one physical photograph, and the `P2002` branch that was written to prevent that never executes. Duplicate custody records in a dispute pack is precisely the harm the feature exists to prevent, and nothing pages anyone.

A second, cheaper instance of the same blindness: `migration.sql` for `20260725010000` was edited after it was first committed (`git log` on that file shows `bfbd3c1b` then `b0b4e3b0`). Prisma stores a checksum of `migration.sql` in `_prisma_migrations`. If any persistent database applied the `bfbd3c1b` version, `prisma migrate deploy` will hard-fail on the next production build with a modified-migration error. CI cannot detect this because it uses an ephemeral database that replays from empty every run. [UNCONFIRMED] — resolve with `SELECT migration_name, checksum, finished_at FROM _prisma_migrations WHERE migration_name LIKE '20260725%'` against every long-lived environment (prod, sandbox, and any shared dev DB) before merging.

I could not close the applied-vs-files question from here. `python3 ~/.claude/skills/engineering-requirements/scripts/migration_drift.py self-test` returned `SELF-TEST PASS` (so the check can fail), but `check --root <repo>` returned `MIGRATION_DRIFT_CANNOT_DETERMINE` with no `DRIFT_DB_URL` in the environment. Per my seat that is a finding, not a skip: the applied state of these two migrations against production is currently unobservable to this review. [UNCONFIRMED]

**Prescription.** Two rules, not two corrections — this comment will otherwise recur on every migration that adds a constraint (METHOD §6):
1. Set `DRIFT_STRICT=1` in `scripts/build.sh` for the production branch. If pre-existing latent unique/nullability drift blocks that today, baseline it in an explicit allowlist file with a ticket per entry, so the *new* objects are gated and the known-bad set is finite and shrinking. A report-only gate on the exact object class this change depends on is not a gate.
2. Extend `check-schema-drift.mjs` to compare foreign keys (`pg_constraint WHERE contype = 'f'`, comparing table, column, referenced table and `confdeltype`) and treat missing-in-db as fatal. A `RESTRICT` that silently became absent is indistinguishable from one that was never written, and this change is the first to depend on one.

## No observation of the live system proves this shipped

The deploy is verified by the control plane, and the control plane is asked the wrong question.

[VERIFIED] `.github/workflows/deploy-check.yml:31` — `run: python3 scripts/verify_deploy.py` is the entirety of the post-push verification.

[VERIFIED] `scripts/verify_deploy.py:112-113` —
```python
            if sha and expected_sha.startswith(sha[:8]) and state in ("BUILDING", "QUEUED", "INITIALIZING"):
                print(f"Vercel:      {sha} [{state}] — in-flight build matches HEAD, parity will settle.")
```
An in-flight build counts as parity and the function returns immediately. So a build that *starts* for this SHA and then fails — including on `build.sh`'s own fail-closed `:6543` exit, or on `check-schema-drift.mjs` exit 1 — produces a green "Deployment Parity Check" and no second look. A failed deploy of this change and a successful one emit the same signal.

[VERIFIED] `scripts/verify_deploy.py:226` — `if "403" in msg or "401" in msg or "invalidToken" in msg:` degrades a token failure to a warning and a pass. Cannot-determine is again treated as a skip.

There *is* a live migration probe, and it does not answer this question either:

[VERIFIED] `app/api/health/migrations/route.ts:75` — `const drifted = failed.length > 0 || rolledBack.length > 0;`
[VERIFIED] `app/api/health/migrations/route.ts:85` — `// Only include names when there's drift — keeps the healthy-path`

It reports the ledger's opinion of itself — `finished_at IS NOT NULL` — which is exactly the value that lies in the no-op scenario the build script documents, and it deliberately withholds the migration names on the healthy path, so an operator cannot ask it "is `20260725010000` applied?". Its Playwright spec lives in `docs/archive/playwright-e2e/health-migrations.spec.ts`, i.e. archived and not run; a grep for `health/migrations` across `app`, `lib`, `scripts` and `.github` finds no caller. Nothing in the pipeline hits it. `smoke-prod.yml` runs `--grep @smoke` against `https://restoreassist.app` on a 15-minute cron and tests availability, not version — it will pass identically against the previous build.

**Prescription.** Name the single observation that proves this change is in effect, and make the pipeline take it. Concretely:
1. Have `/api/health/migrations` return `latest_migration` (the max `migration_name`) and `build_sha` (`process.env.VERCEL_GIT_COMMIT_SHA`) on the **healthy** path, not only on drift. The current payload is a constant that cannot distinguish two releases.
2. Add a post-deploy step to `deploy-check.yml` that, after Vercel reports `READY`, `curl`s that endpoint and asserts `build_sha == github.sha` **and** `latest_migration >= 20260725010000`. That single assertion is the one thing that would have caught the 2026-04-27 P3009 outage, the RA-1807 pooler no-op, and a promotion that silently kept the old alias.
3. Remove the `BUILDING/QUEUED/INITIALIZING` early-return, or make it poll to a terminal state. "A build started" is not "a build shipped".
4. Make the 401/403 branch exit non-zero. A verifier that passes when it cannot see is the same fail-open it exists to catch — and by construction it has never failed, so it is indistinguishable from one that cannot.

**Where the method overruled my instinct:** my domain instinct was to also block on `scripts/build.sh:48` applying migrations un-gated on every production build while the handoff records them as `**NOT executed** — owner-gated (Rule 29)`. Both migrations here are additive and nullable, the schema lands before the code, and I could not name a concrete failure that ordering causes — so under the bar in `CONTRACT.md` it is not a finding and I demoted it to the mechanism paragraph above rather than manufacture a fourth.
