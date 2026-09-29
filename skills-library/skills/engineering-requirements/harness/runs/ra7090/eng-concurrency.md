by: eng-concurrency
contributed: [eng-concurrency]
categories:
  concurrency:    {state: PRESCRIBED, ref: "#unfenced-leases-and-a-retry-guard-that-lets-go", by: eng-concurrency, blocking: true}
  failure_modes:  {state: PRESCRIBED, ref: "#reconciling-an-external-balance-is-not-an-increment", by: eng-concurrency, blocking: true}
  invariants:     {state: PRESCRIBED, ref: "#latest-reading-per-point-has-no-defined-clock", by: eng-concurrency, blocking: true}
cross_domain:
  - "lib/idempotency.ts:328 runs an unbounded `deleteMany` over IdempotencyRecord on every one of 154 mutation routes, with up to 1MB of cached response body per row — eng-data owns the sweep cost and the batching"
  - "app/api/inspections/[id]/drying-status/route.ts:42 caps at `take: 200` readings before assessing drying readiness; a long job silently drops the oldest — eng-data owns whether that truncation is correct"
  - "the evidence POST resolves `storedPhoto` and verifies the manifest outside the transaction that creates the row; correct today because InspectionPhoto is immutable-by-FK-restrict, but that is an unstated dependency — eng-data owns the FK contract"

## Unfenced leases and a retry guard that lets go

Three overlap guards in this codebase are TTL leases with no fencing token and no renewal, and two of them are check-then-act with no constraint behind them. Spec §32 asserts the opposite:

> long-running handlers use leases ≥ their duration; `ScheduledEmail`, `AgentTask`, and cron runners use CAS claims / stale-sweeps / advisory locks [H2–H5]

**(a) `runCronJob` — 29 cron routes, no constraint, 5-minute lease.** `[VERIFIED]` `lib/cron/runner.ts:24-42`:

```ts
const recentRunning = await prisma.cronJobRun.findFirst({
  where: { jobName, status: "running", startedAt: { gte: new Date(Date.now() - 5 * 60 * 1000) } },
});
if (recentRunning) { return { itemsProcessed: 0, status: "skipped", ... }; }
const run = await prisma.cronJobRun.create({ data: { jobName, status: "running" } });
```

`CronJobRun` carries no unique constraint — `[VERIFIED]` `prisma/schema.prisma:4586-4587` is the entire constraint surface: `@@index([jobName, startedAt])` / `@@index([status])`. Two Vercel cron invocations landing milliseconds apart (retry after a cold-start timeout, or a manual `POST` trigger alongside the schedule) both read no running row and both `create`. `[VERIFIED]` no `pg_advisory_lock` or `pg_try_advisory_lock` exists anywhere under `lib`, `app` or `scripts` — grep returns nothing, so §32's "advisory locks" is unbuilt.

The 5-minute window is separately too short for the jobs it guards. `sync-xero-payments` polls up to 100 integrations × 50 invoices with one sequential `fetch` to `api.xero.com` each — up to 5,000 round trips — `[VERIFIED]` `app/api/cron/sync-xero-payments/route.ts:8` (`MAX_XERO_INTEGRATIONS_PER_CRON_RUN = 100`) and `:110` (`take: 50`). It runs every 15 minutes. `process-emails` and `advance-workflows` run `*/5 * * * *` — the schedule interval *equals* the guard window, so every one of those invocations sits exactly on the boundary. Its own comment already believes a slower cadence: `[VERIFIED]` `app/api/cron/sync-xero-payments/route.ts:30` — `// RA-1315: wrap in runCronJob so parallel 4h-cron invocations ... don't both reconcile the same invoices.` The job was rescheduled to 15 minutes (`vercel.json`) and the guard was not resized.

`[INFERENCE]` A stalled run additionally never releases: `status` stays `"running"` forever if the lambda is killed, and the only recovery is the same 5-minute window that creates the overlap. Stall-recovery and overlap-prevention are the same knob, so you cannot tune one without breaking the other.

**Prescription.** Replace the read-then-create with a claim that cannot double-grant: `@@unique([jobName, status])` is wrong (completed rows collide), so use either `pg_try_advisory_lock(hashtext(jobName))` held for the process lifetime, or a `CronJobLease` row with `@@unique([jobName])` claimed by `updateMany({ where: { jobName, OR: [{ heldUntil: { lt: now } }, { heldUntil: null }] }, data: { heldUntil, fenceToken: { increment: 1 } } })` and `count === 1` as the grant. Every write the job performs carries the fence token; a write whose token is stale is refused. Set `heldUntil` per job from its measured p99 duration, never one global constant, and renew it mid-run for the long pollers.

**(b) `withIdempotencyFingerprint` — 60-second reservation, then the loser's response overwrites the winner's.** `[VERIFIED]` `lib/idempotency.ts:252` reserves with `expiresAt: new Date(now.getTime() + 60_000)`, and `:276-279`:

```ts
if (existing.expiresAt < now) {
  await prisma.idempotencyRecord.deleteMany({ where: { cacheKey } });
  return reserveIdempotencySlot({ cacheKey, scope, key, fingerprint, now });
}
```

Concrete interleaving. A field device POSTs evidence; the handler resolves the photo, verifies an Ed25519 signature and runs a two-write transaction on a cold serverless connection and takes 70s. At t=61s the device retries. Request B finds the reservation expired, deletes A's row, reserves its own, and runs the handler **concurrently with A**. At t=70s A completes and executes `[VERIFIED]` `lib/idempotency.ts:400` — `await prisma.idempotencyRecord.update({ where: { cacheKey }, ... })` — which now writes A's status and response body into **B's** reservation. If B has meanwhile failed and deleted the row (`:373` / `:382`), A's `update` throws P2025 *outside* any route-level try/catch, so the client receives a 500 for work that committed successfully. This is the stalled-holder-wakes-up-and-writes pattern verbatim; 154 route files call `withIdempotency`.

The signed-capture path survives this only because it has a real natural key behind the lease — `[VERIFIED]` `prisma/schema.prisma`, `EvidenceItem.captureReplayKey String? @unique`, with the P2002 handled at `app/api/inspections/[id]/evidence/route.ts:472-479`. That is the correct shape and should be the model for the rest.

**(c) The durable per-mutation key exists and does not gate anything.** `[VERIFIED]` `prisma/schema.prisma:7845` — `ClientMutation` carries `@@unique([workspaceId, mutationId])`. `[VERIFIED]` `lib/idempotency.ts:174-176`:

```ts
} catch (err) {
  if (!isUniqueViolation(err)) throw err;
}
```

The constraint fires, the violation is swallowed, and control falls straight through to `response = await handler()` at `:371`. The ledger records that a duplicate arrived; it does not stop it. Combined with `TTL_MS = 24 * 60 * 60 * 1000` (`:28`) and the sweep at `:140-143`, an offline-queued mutation replayed more than 24 hours after its first attempt — a technician whose device sits in airplane mode over a long weekend, which spec §33 explicitly designs for — re-executes for real. The *unsigned* evidence path is exactly this case: `app/api/inspections/[id]/evidence/route.ts:261` creates the row with no replay key and no natural-key constraint, so the replay produces a second EvidenceItem for the same photograph, and §34's chain of custody now shows one capture twice.

**Prescription.** When `createClientMutationLedger` hits P2002, look the existing row up and return its recorded `responseStatus`/`responseBody` rather than proceeding; when the prior row is still `PENDING`, return 409. That makes the mutation id — which the client controls and can persist in its offline queue — the exactly-once key, and demotes `IdempotencyRecord` to what its own comment already calls it (`evidence/route.ts:373`: *"a response CACHE with a 24h TTL"*).

**What would overturn all three.** A measured p99 for every `runCronJob` handler under 5 minutes and for every `withIdempotency` route under 60 seconds, plus a natural-key unique constraint on every write those routes perform. If those exist, the leases are correctly sized and this finding is noise. `[UNCONFIRMED]` — the query that settles it: `SELECT "jobName", max("durationMs"), percentile_cont(0.99) WITHIN GROUP (ORDER BY "durationMs") FROM "CronJobRun" WHERE "startedAt" > now() - interval '30 days' GROUP BY 1 ORDER BY 2 DESC;` and, for overlaps already in prod, a self-join on `CronJobRun` for rows of the same `jobName` whose `[startedAt, completedAt]` intervals overlap.

## Reconciling an external balance is not an increment

Spec §22 states the rule:

> Manual, EFT, partial, credit, and refund are recorded via atomic in-transaction `increment`/`decrement`; status is derived from the resulting row (fixes RA-ARCH-02 C2). The Stripe webhook writes an `InvoicePayment` row and maintains `amountPaid` (no PAID-without-ledger).

The rule is unimplementable as written for the accounting-reconciliation path, and both live writers already break it in the way the rule's own wording invites.

`[VERIFIED]` `lib/integrations/xero/webhook-processor.ts:301-327` — read, compute, absolute assignment, no ledger row, no CAS predicate:

```ts
const invoice = await prisma.invoice.findFirst({ where: { externalInvoiceId: xeroInvoiceId }, select: { id: true, status: true, totalIncGST: true } });
if (!invoice || invoice.status === "PAID") { return; }
const newAmountPaid = Math.max(0, (invoice.totalIncGST ?? 0) - amountDueCents);
await prisma.invoice.update({ where: { id: invoice.id }, data: { amountPaid: newAmountPaid, amountDue: amountDueCents, ... } });
```

`[VERIFIED]` `app/api/cron/sync-xero-payments/route.ts:152-160` — the poller blind-writes the terminal money status with no ledger row at all:

```ts
await prisma.invoice.update({
  where: { id: invoice.id },
  data: { status: "PAID", paidDate: xeroInvoice.FullyPaidOnDate ? new Date(...) : new Date() },
});
```

The interleaving that costs money. An invoice for $8,400 receives two Xero part-payments 40ms apart. Both `payment.created` webhooks fetch the payment from Xero; Xero returns `Invoice.AmountDue` that is stale for one of them (say both see `AmountDue = 4200`). Both compute `newAmountPaid = 4200` and both write it. `amountPaid` is $4,200 against $8,400 of received money, and there is no ledger to reconcile against because no `InvoicePayment` row was written. Nothing detects this until a human reads a statement. `invoice.status === "PAID"` at `:306` is a check-then-act on the same read: a partial-payment webhook that read before the full-payment webhook's write will pass the guard and write a *lower* `amountPaid` over a settled invoice, flipping a paid invoice back to unpaid.

Spec §23 makes this reach further than the money field:

> **validated financial state** — an invoice must exist and be reconciled (issued with a balancing payment ledger)

An invoice marked PAID by either path above has `amountPaid` set and zero `InvoicePayment` rows, so it can never satisfy that closure gate. The pressure at that point will be to weaken the gate, which is how "reconciled" quietly becomes "status says PAID".

**The requirement §22 is missing.** `increment` expresses "a payment arrived"; it cannot express "the external system says the remaining balance is now zero". Xero, QBO and MYOB report absolute balances, so the reconciliation path is structurally a different operation from the manual-payment path and §22 currently gives it no rule. Specify:

1. Every external settlement writes an `InvoicePayment` row keyed on the provider's own payment id — `@@unique([provider, externalPaymentId])` — and money is only ever moved by inserting that row. This turns duplicate webhook delivery and duplicate cron-poll observation into a constraint violation instead of a lost update, and it is the "constraint-backed dedupe" §22 already promises for Stripe, applied to the accounting providers too.
2. `Invoice.amountPaid` is derived in the same transaction as the insert, as `SUM(InvoicePayment.amount)`, never assigned from an external absolute.
3. The status write carries a CAS predicate: `updateMany({ where: { id, status: { in: [...expected] }, version }, data: { ... } })`, and `count === 0` means re-read and re-derive, never silently proceed.
4. Name the arbitration rule for when the external absolute balance and the local ledger sum disagree. Right now nothing in the spec says which wins, so an implementer will pick one per call site — which is what produced these two divergent writers.

**What would overturn this.** A `@@unique` on an external payment identifier that I missed, plus a reconciliation job that asserts `SUM(InvoicePayment) = Invoice.amountPaid` and has never fired. `[UNCONFIRMED]` — run against prod: `SELECT i.id, i."amountPaid", COALESCE(SUM(p.amount),0) AS ledger FROM "Invoice" i LEFT JOIN "InvoicePayment" p ON p."invoiceId" = i.id WHERE i.status = 'PAID' GROUP BY i.id, i."amountPaid" HAVING i."amountPaid" <> COALESCE(SUM(p.amount),0);` — a non-empty result is the PAID-without-ledger population that already exists. Positive control before trusting a zero row count: confirm `InvoicePayment` has rows at all.

## Latest reading per point has no defined clock

Spec §14 makes an ordering the load-bearing input to a compliance decision, and never says whose clock decides it:

> Current drying state is computed from the **latest valid reading per monitoring point / material / assembly / room**.

`[VERIFIED]` `prisma/schema.prisma:2346` — the only time field on the model is `recordedAt DateTime @default(now())`, which is the **server's insert time**, not the field capture time. There is no `capturedAt` on `MoistureReading`, and the moisture write route does not set `recordedAt` (grep for `recordedAt` under `app/api/inspections/[id]/moisture/` returns nothing). `[VERIFIED]` `app/api/inspections/[id]/drying-status/route.ts:41` — `orderBy: { recordedAt: "desc" }` — so "latest" today means "most recently synced".

The interleaving. Two technicians work the same claim. Tech A reads monitoring point MP-3 at 09:00 at 22% WME and stays offline in a basement until 16:00. Tech B reads MP-3 at 14:00 at 14% WME and syncs immediately. Both rows land with `recordedAt` = their sync instant, so A's 09:00 reading is the "latest" row and the certification guard evaluates a seven-hour-old 22% as current. The structure is dry and will not certify, or — with the numbers reversed, which is equally likely — a still-wet structure certifies and the drying record says so under §34's "immutable evidence" banner. Spec §33 designs explicitly for exactly this delay:

> Offline-first field capture with durable mutation queue, per-mutation idempotency keys, stale-processing recovery, and version-preconditioned replay

`[INFERENCE]` The obvious repair — trust a client-supplied capture timestamp — trades one failure for a worse one. The signed-capture work in this repo already reached that conclusion and wrote it down; `lib/evidence/capture-manifest.ts:106-111` calls the client capture time *"the client-asserted capture time, which an attacker controls"* and refuses to let it decide revocation. Moisture readings drive a certification that ends up in an insurer dispute, so they need at least the same care.

**Prescription.** Amend §14 to state the ordering key explicitly, and add the field:

1. `MoistureReading.capturedAt` (client-asserted, required, never rewritten) alongside `recordedAt` (server receipt, never client-writable) — the same two-clock split the capture manifest already uses.
2. "Latest valid reading per point" means max `capturedAt` among non-invalidated readings, with `recordedAt` as the deterministic tiebreak for identical `capturedAt`.
3. A reading whose `capturedAt` is after its own `recordedAt`, or more than a bounded skew ahead of it, is flagged rather than silently ordered — a device with a wrong clock is a real event, not an attack, and it must be visible instead of quietly reordering a drying log.
4. The assertion to test: *for every monitoring point, the reading the certification guard selects is the one with the greatest `capturedAt`, and this holds when the rows are inserted in reverse `capturedAt` order.* That test is cheap and is the positive control that proves the ordering is not accidentally coming from insert order.

**Where the method overruled my instinct.** My instinct was to prescribe a hybrid logical clock per device. METHOD §1 wins: nobody has tried the boring version, and a required `capturedAt` column with a skew flag is the boring version. If skew turns out to be routine rather than exceptional in the field data, revisit.

`[UNCONFIRMED]` — the observation that would settle whether this already bites: `SELECT count(*) FROM "MoistureReading" a JOIN "MoistureReading" b ON a."inspectionId" = b."inspectionId" AND a.location = b.location AND a."surfaceType" = b."surfaceType" AND a.id <> b.id WHERE a."recordedAt" > b."recordedAt" AND abs(extract(epoch FROM (a."recordedAt" - b."recordedAt"))) < 60;` — clusters of same-point readings arriving within seconds of each other are batch-synced offline queues whose true capture order is already lost.
