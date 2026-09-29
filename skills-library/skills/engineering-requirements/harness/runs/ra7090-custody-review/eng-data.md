by: eng-data
categories:
  data_model: {state: PRESCRIBED, ref: "#a-null-contenthash-has-three-meanings-and-the-schema-declares-none", by: eng-data, blocking: true}
  migration:  {state: PRESCRIBED, ref: "#historical-rows-need-a-marker-not-a-backfill", by: eng-data, blocking: true}
  invariants: {state: PRESCRIBED, ref: "#every-evidenceitem-has-at-least-one-custodyevent-is-enforced-in-one-of-three-writers", by: eng-data}
cross_domain:
  - "the unsigned branch has no durable replay key, so a 500 from the new transaction retried without an Idempotency-Key header creates a second evidence row and a second CAPTURED event — eng-concurrency owns the retry contract"
  - "no test in the unsigned describe block asserts custodyEventCreate was called; the three atomicity tests at native-capture-custody.test.ts:823-848 all drive nativeCaptureBody(), the signed path — eng-test owns the missing oracle"
  - "buildEvidenceCustodyExport surfaces custody[].metadata as `unknown` so assetBacked is not part of the typed contract — eng-contract owns whether the export type should name it"

## A null contentHash has three meanings and the schema declares none

For **new** writes through this branch the null is actually unambiguous, and the guard that makes it so is upstream, not in the diff:

`app/api/inspections/[id]/evidence/route.ts:232` [VERIFIED]
> `if (originalPhotoId && (!storedPhoto?.cocoaSha256 || storedPhoto.fileSize === null)) {`

Because that 400s, `storedPhoto` non-null implies `cocoaSha256` non-null, so `contentHash: storedPhoto?.cocoaSha256 ?? null` (line 317) is null **exactly when no photo was referenced**. The `?? null` is defensive, not a hole. Good.

The problem is that this is true only by a coincidence of control flow in one route, and no reader can see it. Three concrete readers, three different wrong conclusions:

1. **The CAPTURED event written here** — null means "not asset-backed".
2. **The ARCHIVED tombstone at line 622** — `contentHash: evidence.hashSha256` [VERIFIED], which is null on any hash-less legacy row. Same column, same null, means "we never knew the hash", not "there were no bytes".
3. **Any future writer** (REVIEWED, ANNOTATED, EXPORTED are all in `CustodyAction`, `prisma/schema.prisma:7985-7994` [VERIFIED]) — null will mean "I did not bother".

The diff's own disambiguator is `assetBacked: Boolean(storedPhoto?.originalStoragePath)` (line 321), buried inside a `JSON.stringify` into `metadata String?`. It is computed from a *different* field (`originalStoragePath`) than the one it explains (`cocoaSha256`), and the export hands it out as opaque:

`lib/evidence/manifest-export.ts:281` [VERIFIED]
> `metadata: parseJsonSafe(event.metadata) ?? event.metadata,`

So a third party verifying a dispute pack offline reads `contentHash: null` with no typed field telling them whether that is expected. That is a decision made silently — the meaning of a null lives in a comment in a route file.

**Prescription.** Promote the distinction out of the JSON blob. Cheapest version that needs no DDL: make the export type carry it, since `assetBacked` is already computed at write time — add `contentHashAbsentReason: "NOT_ASSET_BACKED" | "PREDATES_HASHING" | null` to `CustodyEventRowForExport` derived from parsed metadata, and make its absence on a null-hash event itself a visible `UNKNOWN`. If you would rather have it queryable and constrainable, a `CustodyEvent.assetBacked Boolean` column plus `CHECK (NOT "assetBacked" OR "contentHash" IS NOT NULL)` moves the guard at line 232 from one route into the database, where the batch route cannot bypass it (METHOD #8: prefer the failure that cannot commit).

One smaller silent default in the same write: `ipAddress` is in the schema (`prisma/schema.prisma:8176`) and is written by nothing — this event sets `userAgent` and leaves `ipAddress` null, as does the signed path at line 496. spec.md §34 asks for "signature capture with IP/UA/timestamp". Either write it or drop the column; a nullable column that every writer leaves null is the one my seat gets paged for six months later.

## Historical rows need a marker, not a backfill

The diff's comment states the blast radius honestly:

`app/api/inspections/[id]/evidence/route.ts:263-269` [VERIFIED]
> `// native capture that fell back to unsigned produced an evidence item`
> `// with an empty custody chain — and because device signing is still`
> `// hardware-blocked, that is currently every evidence item in the`
> `// system.`

And the reader it lies to is exact. `custodyPagination.complete` is derived only from the cursor:

`lib/evidence/manifest-export.ts:316` [VERIFIED]
> `complete: (input.custodyNextCursor ?? null) === null,`

Zero events, no cursor, `complete: true`. The dispute pack then renders it in words:

`lib/dispute-pack.ts:1315-1316` [VERIFIED]
> `const noun = custody.custodyEventTotal === 1 ? "custody event" : "custody events";`
> `return `${custody.custodyEventTotal} ${noun} (complete)`;`

That is the string **"0 custody events (complete)"** printed into a claim-defence PDF. This change stops producing new rows in that state; it does nothing about the ones already there, and nothing about what the export says for them.

**Do not backfill.** Synthesising a CAPTURED event from an evidence row's `createdAt`/`capturedById` fabricates a custody fact nobody observed, and it does it in the one table whose whole value is that it only records observations. It would also be indistinguishable from a genuine event afterwards — the migration would destroy the very information you are trying to preserve.

**Prescribe a marker, and make `complete` unable to lie.** Boring version first (METHOD #1), no DDL:

1. Freeze one constant `CUSTODY_EVENTS_GUARANTEED_FROM` — a UTC instant set to the **end** of this change's rollout, not its start. The rollout window matters: while old and new instances are both serving, rows land from both, so any row with `createdAt` inside the window is ambiguous and must be treated as unknown, not as complete.
2. In `buildEvidenceCustodyExport`, when `totalCount === 0` and `evidence.createdAt < CUSTODY_EVENTS_GUARANTEED_FROM`, emit `complete: false` with a reason (`"PREDATES_CUSTODY_EVENT_RECORDING"`). An empty chain after the cutoff is a genuine anomaly and should stay `complete: true` so it is visibly wrong.
3. `formatCustodyHistoryNote` gets a third branch so the pack says "custody events not recorded for captures before <date> — see legacy capture note" rather than "(complete)".

If a frozen constant is not crisp enough for your deploy topology, the DDL version is a nullable `EvidenceItem.custodyRecordedFrom DateTime?` written at insert. Additive, nullable, no table scan, no lock — the pattern this repo already used at `docs/superpowers/specs/2026-05-14-tradie-evidence-capture-ui-design.md:310` [VERIFIED]:
> `Additive only. Existing rows backfill to NULL. NIR report renderer flags `cocoaSha256 == null` rows as "legacy capture (chain-of-custody not verified)".`

That is the same problem solved the same way one layer down; reuse it rather than inventing a second convention.

**Size the gap before choosing.** [UNCONFIRMED] — I cannot reach the database from this seat. Run against a read replica:
```sql
SELECT count(*) AS total,
       count(*) FILTER (WHERE c.evid IS NULL) AS no_custody_events,
       min(e."createdAt") FILTER (WHERE c.evid IS NULL) AS earliest,
       max(e."createdAt") FILTER (WHERE c.evid IS NULL) AS latest
FROM "EvidenceItem" e
LEFT JOIN LATERAL (
  SELECT 1 AS evid FROM "CustodyEvent" x WHERE x."evidenceItemId" = e.id LIMIT 1
) c ON true;
```
If `latest` is after this change deploys, a writer is still bypassing the transaction — see the next section. Positive control before trusting a zero: the same query with the `LEFT JOIN LATERAL` predicate inverted must return a non-zero count, or your join is wrong and the null result is meaningless.

Separately, and cheap: `pg_dump --schema-only -t '"CustodyEvent"' -t '"EvidenceItem"'` diffed against `prisma/schema.prisma:8167-8184`. The table was created by an `IF NOT EXISTS` adoption migration (`prisma/migrations/20260705060000_ra6996_adopt_orphan_tables_and_columns/migration.sql:179` [VERIFIED]: `CREATE TABLE IF NOT EXISTS "CustodyEvent" (`), which is exactly the shape that silently tolerates a deployed table differing from the declared one — the migration ledger and the ORM agree with each other and neither has ever been compared to the database.

## "Every EvidenceItem has at least one CustodyEvent" is enforced in one of three writers

State it as the assertion: *for every row in `EvidenceItem` created at or after the cutoff, `EXISTS (SELECT 1 FROM "CustodyEvent" WHERE "evidenceItemId" = id)`.*

After this change, three writers create `EvidenceItem` rows and one satisfies it:

- `app/api/inspections/[id]/evidence/route.ts:274` + `:307` — fixed by this diff.
- `app/api/inspections/[id]/evidence/route.ts:443` + `:484` — signed path, already correct.
- `app/api/inspections/[id]/evidence/batch/route.ts:255` [VERIFIED] — `return prisma.evidenceItem.create({`, inside a `Promise.allSettled` over uploads, no custody event, no transaction. Yes, the gap the question asks about is open here, and it is the *higher*-volume path: this is the drag-a-folder-of-photos flow.
- `app/api/inspections/[id]/evidence/promote-client/route.ts:56` [VERIFIED] — `prisma.evidenceItem.create({` inside a batched `prisma.$transaction(ops)`. Same gap, and worse in kind: this route's own header comment (line 13) says the promotion means the item "now belongs to the chain-of-custody record", and it writes no chain-of-custody row. The staff verification act — the single most disputable event in the whole flow — is recorded only in a display string, `capturedByName: \`Client (verified by ${reviewerName})\`` (line 64). A mutable name field masquerading as an audit trail is what spec.md §34 closes with a sentence banning.

METHOD #4 applies: this is a half-finished migration. Two of four write paths now emit custody events and two do not, so the system has two truths and no rule for which wins — and the marker prescribed above will label post-cutoff batch rows as a *genuine anomaly* rather than a legacy gap, which is worse than the status quo, because it will read as tampering.

METHOD #6 applies to the fix: patching the two routes leaves this as a code-review comment somebody has to make again the next time an evidence writer is added. Make it structural. In order of cost:

1. **Now, blocking:** wrap the batch and promote-client creates the same way this diff wraps the unsigned branch. Batch is `Promise.allSettled` per file — one `$transaction` per file (row + event), not one across the batch, so partial success keeps working and each file is independently atomic. Promote-client already has a `$transaction(ops)`; it needs the custody create appended to `ops`, but `ops` is declarative so it needs the created id — convert to the interactive form as this diff did.
2. **Then, so it stays fixed:** a `pg_trigger` `AFTER INSERT ON "EvidenceItem"` is the wrong tool (it would fabricate an actor). The right rule is a scheduled assertion — the query in the previous section run as a check with a threshold of zero for rows after the cutoff — plus a lint/CI grep that `evidenceItem.create` never appears outside a `$transaction` callback. The check that catches the fourth writer nobody has written yet is worth more than the two fixes.

**What would overturn all of this** (METHOD #2): if the batch and promote-client routes are being retired in the same release and evidence creation collapses to the one endpoint, the invariant becomes single-writer and the structural check is over-engineering — fix the two routes and skip step 2. I could not find evidence either way in the working tree.
