by: eng-failure
contributed: [eng-failure]
categories:
  failure_modes: {state: PRESCRIBED, ref: "#unsigned-custody-stops-at-the-route-boundary", by: eng-failure, blocking: true}
  concurrency:   {state: PRESCRIBED, ref: "#default-transaction-timeouts-on-the-universal-write-path", by: eng-failure, blocking: true}
  test_oracle:   {state: PRESCRIBED, ref: "#the-only-test-of-this-branch-mocks-a-prisma-without-transactions", by: eng-failure, blocking: true}
  data_model:    {state: N/A, reason: "No schema change. CustodyEvent.contentHash and metadata were already nullable columns and the write adds no column, index or relation."}
  rollback:      {state: N/A, reason: "Reverting this diff is a pure code revert. The CAPTURED rows it wrote stay valid and readable — an append-only child table with no unique constraint means the reverted build simply stops appending, so there is no 3am sequence to design."}
cross_domain:
  - "every EvidenceItem written before this change still has an empty custody chain and the diff ships no backfill — eng-data owns the migration and whether a synthetic CAPTURED event is honest"
  - "the invariant 'every EvidenceItem has exactly one CAPTURED event' is now true on one write path and false on two — eng-data owns stating and enforcing it"
  - "batch/route.ts writes originalStoragePath both as a column and inside structuredData JSON (lines 274-279) — an unfinished migration eng-data owns"

## Unsigned custody stops at the route boundary

The diff's own justification names three populations: `every web-browser capture, every batch upload, and every native capture that fell back to unsigned` (`app/api/inspections/[id]/evidence/route.ts:263-265`). It fixes one of them. Batch upload creates evidence through a different client and writes no custody event at all.

`[VERIFIED]` `app/api/inspections/[id]/evidence/batch/route.ts:255` — `        return prisma.evidenceItem.create({` — a bare create inside `Promise.allSettled`, with no `$transaction`, no `custodyEvent`, and no `withIdempotency` wrapper. Nothing in the diff touches this file.

Concrete scenario: a technician drags 12 photos into the batch uploader. Twelve `EvidenceItem` rows land with `deviceType: "WEB_BROWSER"` and zero `CustodyEvent` rows. Six weeks later `GET /api/inspections/{id}/evidence/{evidenceId}/custody` returns exactly the artifact the comment says this change prevents: `custodyPagination: {returnedCount: 0, totalCount: 0, complete: true}` (`lib/evidence/manifest-export.ts:312-317` — `      returnedCount: custody.length,` / `      complete: (input.custodyNextCursor ?? null) === null,`). `complete: true` is about pagination, not chain completeness, and a dispute-pack reader has no way to tell those apart. The change makes this *worse in kind*: the population is now split into rows whose empty chain means "written by batch" and rows whose empty chain means nothing was ever recorded, with no field distinguishing them.

Second half of the same failure, and the answer to the `contentHash: null` question: null is the **correct value** — writing a client-asserted hash there would be worse — but it was chosen without noticing it produces a chain that *looks* populated while binding no bytes. The reachable case is not exotic: `PHOTO_DAMAGE` with `deviceType` absent or `WEB_BROWSER` and a client-supplied `fileUrl` never reaches the fail-closed guard, because that guard requires both photographic **and** native.

`[VERIFIED]` `app/api/inspections/[id]/evidence/route.ts:205` — `        if (isPhotographic && isNativeCapture && !originalPhotoId) {`

So a browser-uploaded photograph produces `hashSha256` unset, `contentHash: null`, `assetBacked: false`, and one CAPTURED event. The export shows `integrity: "UNSIGNED"` and a one-entry custody array. A reader sees a chain of custody for a photograph where nothing in that chain covers the photograph's bytes. `[VERIFIED]` that this path is live and expected: `app/api/inspections/[id]/evidence/__tests__/native-capture-custody.test.ts:351` — `  it("still accepts non-photographic evidence with no asset (no regression)", async () => {`.

**Prescription**, in the order that closes the most damage per unit of work:

1. Write the CAPTURED event in `batch/route.ts` inside the same `$transaction` as each `evidenceItem.create`, with `contentHash: uploaded.sha256` (which that route already has — `batch/route.ts:271` `            hashSha256: uploaded.sha256,`). Batch is the *easier* case: it always has a server-computed digest.
2. Add a detector before adding any reconciliation machinery. Method #1 over my own instinct here — my reflex is a nightly compensating job that back-fills orphans, and the boring version wins: a single read-only query, `SELECT count(*) FROM "EvidenceItem" e WHERE NOT EXISTS (SELECT 1 FROM "CustodyEvent" c WHERE c."evidenceItemId" = e.id AND c.action = 'CAPTURED')`, alerted on **non-zero absolute count, not rate**. A job or path that stops writing custody events produces zero errors; only an absence check catches it.
3. Surface `assetBacked` as a first-class field on the export rather than as free-form JSON inside `metadata`, so a dispute-pack reader is told the bytes are uncovered instead of having to parse for it.

## Default transaction timeouts on the universal write path

The new `$transaction` passes no options, so it takes Prisma's defaults.

`[VERIFIED]` `app/api/inspections/[id]/evidence/route.ts:273` — `          const evidenceItem = await prisma.$transaction(async (tx) => {` — closed at line 328 with `          });`, no second argument.

This repo has already been paged for exactly this and wrote the lesson down.

`[VERIFIED]` `app/api/auth/register/route.ts:222` — `        // RA-4989 — Prisma's default maxWait is 2s and default timeout is 5s.` — and the remedy at `app/api/auth/register/route.ts:231` — `        { maxWait: 10_000, timeout: 30_000 },`. The RA-4989 comment names the trigger verbatim: sandbox DB latency of 2-4s and connection-pool cold starts pushing transaction *start* past 2s, producing `"Transaction API error: Unable to start a transaction in the given time"`.

The pool this runs against is small and per-invocation.

`[VERIFIED]` `lib/prisma.ts:17` — `    max: 5,` — with `connectionTimeoutMillis: 20_000` on the line below.

`[INFERENCE]` The mechanism, and why this diff changes the blast radius rather than merely inheriting it: an interactive transaction holds one of those five connections for BEGIN + two INSERTs + COMMIT, roughly four round trips where the previous code used one. `maxWait: 2000` fails *faster* than the pool's own 20s `connectionTimeoutMillis`, so under pool pressure the transaction is the first thing in the request to give up. Concretely: a mobile client comes back online and flushes a queue of 20 evidence POSTs against one warm serverless instance. Requests 6+ contend for five connections; each also runs six non-transactional idempotency queries (`cleanupExpiredIdempotencyRecords`, the reserve `create`, the ledger `create`, the record `update`, the ledger `updateMany`). The `$transaction` calls hit `maxWait` and throw P2028, which `fromException` maps to a 500 (`lib/api-errors.ts:163` — `    status: 500,`), which makes `withIdempotencyFingerprint` delete the reservation (`lib/idempotency.ts:382` — `    await prisma.idempotencyRecord.deleteMany({ where: { cacheKey } });`) so the offline queue retries — into the same exhausted pool. That is the brownout-to-outage shape: the retry keeps the dependency down after it tries to recover. Before this diff the unsigned branch was a single INSERT that would queue on the pool for up to 20s and succeed.

The change is stated to make this the path for 100% of live traffic: `because device signing is still hardware-blocked, that is currently every evidence item in the system` (`route.ts:265-266`). A pattern that was acceptable on the rare signed path is now the universal one.

**Prescription:** pass `{ maxWait: 10_000, timeout: 30_000 }` to both `$transaction` calls in this file — the new one at line 273 and the pre-existing signed one at line 442 — copying RA-4989 rather than re-deriving it. Per method #6, the recurrence is the finding: this is the third `$transaction` in the repo to take the defaults after RA-4989 documented why they are wrong, so the durable fix is a lint rule requiring an explicit options object on `prisma.$transaction(fn)`, not three more corrections.

## The only test of this branch mocks a prisma without transactions

`app/api/inspections/[id]/evidence/__tests__/route.test.ts` is the one test file that drives the unsigned POST branch, and its prisma double has no `$transaction` and no `custodyEvent`.

`[VERIFIED]` `app/api/inspections/[id]/evidence/__tests__/route.test.ts:86` — `vi.mock("@/lib/prisma", () => ({` — the object literal that follows exposes only `evidenceItem.create`, then `app/api/inspections/[id]/evidence/__tests__/route.test.ts:91` — `    idempotencyRecord: mocks.idempotencyRecord,` and a `clientMutation` stub. No `$transaction` key.

`[INFERENCE]` `prisma.$transaction` is therefore `undefined` in that suite. Line 273 throws a `TypeError`, the enclosing `try` catches it, `fromException` returns 500, and the single assertion in the file fails: `app/api/inspections/[id]/evidence/__tests__/route.test.ts:138` — `    expect(response.status).toBe(201);`. I did not run it — I am read-only. The command that settles it is `npx vitest run "app/api/inspections/[id]/evidence/__tests__/route.test.ts"`, and a passing result would overturn this finding, in which case the mock is resolving `$transaction` from somewhere I did not find.

The second half is the one that matters more, because a red test gets fixed and a missing test does not. **The new behaviour has no test.** The atomicity suite covers only the signed path.

`[VERIFIED]` `app/api/inspections/[id]/evidence/__tests__/native-capture-custody.test.ts:774` — `describe("POST — evidence row and CAPTURED event commit atomically", () => {` — every `it` inside it (lines 823, 833, 848) builds its request from `nativeCaptureBody()`, i.e. the signed envelope. The pre-existing unsigned tests (lines 282, 300, 318, 351) assert only on `evidenceItemCreate` and predate the change; they will pass unchanged whether or not the custody event is written.

So the diff can be reverted, or the `tx.custodyEvent.create` call deleted, and the suite stays green. That is the same absent-check failure as the batch route, one level up.

**Prescription — three tests, all in `native-capture-custody.test.ts` against its `$transaction` fake with real rollback semantics:**

1. An unsigned asset-backed capture writes exactly one CAPTURED event with `contentHash` equal to the photo's `cocoaSha256`.
2. An unsigned capture with no stored asset writes exactly one CAPTURED event with `contentHash: null` and `assetBacked: false` — pinning the deliberate null so a future change cannot quietly substitute a client-supplied hash.
3. `custodyEventCreate.mockRejectedValueOnce(...)` on the **unsigned** body commits neither row — the mirror of line 823, which today only proves it for signed captures.

Then repair `route.test.ts`'s prisma double by adding `$transaction` and `custodyEvent`. Per method #6 again, the recurring shape is a hand-rolled prisma mock per test file drifting from the client the route actually uses: the rule is one shared prisma test double, not four corrections.
