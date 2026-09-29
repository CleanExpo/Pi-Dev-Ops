by: eng-concurrency
categories:
  concurrency: {state: PRESCRIBED, ref: "#two-drains-one-queue", by: eng-concurrency, blocking: true}
  invariants:  {state: PRESCRIBED, ref: "#at-most-once-has-nowhere-to-be-enforced", by: eng-concurrency, blocking: true}
  test_oracle: {state: PRESCRIBED, ref: "#no-seam-to-run-the-drain-twice", by: eng-concurrency}
cross_domain:
  - "the lost update on retryCount means MAX_RETRY_COUNT never fires, so a poisoned entry POSTs forever — eng-failure owns the blast radius of that amplification"
  - "vitest.config.ts includes only lib/**/__tests__/** and app/**/__tests__/**, while the only test file is __tests__/engine.test.ts at the repo root, so zero tests execute — eng-test owns that"
  - "003_rls_fix.sql is in migrations/ but APPLIED_LEDGER.txt lists only 001 and 002 — eng-release owns the unapplied migration"
  - "getSyncStatus counts a 'conflict' status that Entry's union type does not contain and no code path ever writes, so SYNC_CONFLICT is unreachable and 'failed' entries report as SYNCED — eng-observability owns the misleading status"

---

## Two drains, one queue

`drainQueue` is a check-then-act loop with an unbounded network call between the check and the act, and nothing marks an entry as in-flight.

The read: [VERIFIED] `lib/sync-queue.ts:24-25`

> `const index = db.transaction("queue").objectStore("queue").index("status");`
> `const entries: Entry[] = await getAll(index, "pending");`

The act, one `await fetch` later: [VERIFIED] `lib/sync-queue.ts:38-39`

> `if (!response.ok) await incrementRetry(db, entry);`
> `else await removeEntry(db, entry.id);`

Three separate mechanisms fail here, and all three are live the moment a second caller exists:

**1. No claim, so both drains send everything.** `db.transaction("queue")` with no mode argument is `readonly`, and an IndexedDB transaction commits as soon as its last request settles — long before the first `await fetch` returns. So the pending set is read in one transaction and every `put`/`removeEntry` runs in a fresh one, with an unbounded HTTP call in the gap. Nothing writes an in-flight marker in between. Concrete interleaving: technician's device regains connectivity, the `online` handler calls `drainQueue`; 40ms later a `visibilitychange` or service-worker `sync` event calls it again. Both `getAll("pending")` return the same three entries, both POST all three. Six report submissions, three intended. [INFERENCE] on the IndexedDB transaction-lifetime mechanism — this is the standard auto-commit behaviour, and it is how every "my queue double-sent" bug I have chased was built.

**2. Lost update on `retryCount`.** [VERIFIED] `lib/sync-queue.ts:16-20`

> `await put(db, {`
> `    ...entry,`
> `    retryCount: entry.retryCount + 1,`

`entry` is a snapshot taken at `getAll` time and `put` writes the whole record. Two drains that both read `retryCount: 0` both compute `1` and both write `1`. The counter advances once per round instead of twice, so a permanently failing entry never reaches `MAX_RETRY_COUNT` and never reaches `markFailed`. The spread also clobbers every other field back to its snapshot value, so any status another writer set during the fetch window is silently reverted to `pending`.

**3. Replay order is not capture order.** [VERIFIED] the `Entry` type at `lib/sync-queue.ts:5-12` has no sequence, no `capturedAt`, no `deviceId`:

> `export type Entry = {`
> `  id: string;`

`getAll` over an index returns records ordered by index key then primary key, and the primary key here is `id`. If `id` is a uuid, the queue replays in random order. A technician who corrects a reading and captures it twice offline has a 50% chance of the server applying the correction first and the stale value second, and nothing in the payload lets the server detect it.

**Prescription — all three must be closed before this becomes code:**

- Give `Entry` a `sending` status and a `leaseExpiresAt`. Claim the batch in a single `readwrite` transaction that reads `pending` and flips it to `sending` before any `fetch` is issued; a drain only picks up entries that are `pending`, or `sending` with an expired lease. That is what makes a second concurrent drain a no-op rather than a doubling.
- Never write the whole record back. `incrementRetry` must re-read the entry inside its own `readwrite` transaction and increment from the stored value, not from the closure snapshot.
- Add a monotonic `seq` (per-device counter) and `deviceId` to `Entry`, drain in `seq` order, and have the server reject or ignore a write whose `seq` is below the last one it accepted for that record. Timestamps generated on a technician's tablet are not usable for ordering — device clocks in the field are wrong by minutes.

## At-most-once has nowhere to be enforced

The client cannot distinguish "the server never received it" from "the server received it and the response was lost". Both land in the same branch: [VERIFIED] `lib/sync-queue.ts:40-41`

> `} catch {`
> `      await incrementRetry(db, entry);`

A tablet that loses its connection after the POST is written to the socket but before the response arrives will retry a request the server already committed. That is not exotic — it is the normal failure of the exact connectivity the spec targets ("Offline capture must survive poor connectivity and retry"). At-least-once delivery is the ceiling this design can reach; the only thing that makes it safe is a durable dedup key.

There is no such key. The request carries no idempotency header — [VERIFIED] `lib/sync-queue.ts:35`

> `headers: { "content-type": "application/json" },`

— and the destination table has nothing to dedup against. [VERIFIED] `supabase/migrations/001_init.sql:1-6`

> `  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),`

The primary key is generated server-side per insert, so two replays of the same payload are two distinct legitimate rows. `grep -rni "unique\|idempot\|ON CONFLICT" .` over the whole fixture returns exactly one hit, `email String @unique` in `lib/schema.prisma:3`. Nothing else in the repo can reject a duplicate.

The invariant, stated so it can be tested: *for any queue entry, the number of report rows attributable to it is exactly one, regardless of how many times `drainQueue` posts it.*

Enforce it in the database, not in application code:

- Add a client-generated `idempotency_key uuid NOT NULL` column to `public.reports` with `UNIQUE (tenant_id, idempotency_key)`, populated from `entry.id` and sent in the request body or an `Idempotency-Key` header.
- The write becomes `INSERT ... ON CONFLICT (tenant_id, idempotency_key) DO NOTHING RETURNING id`, and the handler returns 200 with the existing id on conflict so the retry sees `response.ok` and calls `removeEntry`.
- `entry.id` must be generated once at capture time and never regenerated on retry, or the key is not stable and the constraint buys nothing.

This is the cheap version of the whole finding: with that constraint in place, every interleaving in `#two-drains-one-queue` degrades from duplicate data to wasted requests.

## No seam to run the drain twice

The concurrency findings above are all reachable by a deterministic test, and none of them can be written against the current signature. `drainQueue(db)` reaches for the ambient global `fetch` — [VERIFIED] `lib/sync-queue.ts:33`

> `const response = await fetch(entry.endpoint, {`

so a test cannot hold the first call's response open while starting a second drain, which is the only interleaving that demonstrates the bug. `RETRY_BACKOFF_MS` and `Date.now()` are likewise reached for directly at `lib/sync-queue.ts:15`, so any retry-count test either sleeps for real or does not run the backoff path at all.

What must exist before this is called done:

- `drainQueue(db, deps)` taking an injected `fetch` and `now()`. Not for purity — because the oracle needs to suspend one request mid-flight.
- A test that starts two `drainQueue` calls against one fake IndexedDB with a single `pending` entry, resolves neither fetch until both have read the queue, and asserts the injected fetch was called **once**. That test fails today and is the proof the lease works.
- A test that resolves the fetch and then rejects it, asserting the stored `retryCount` is `2` and not `1` — the lost-update oracle.
- A test asserting entries are posted in ascending `seq`, seeded with entries whose `id` sort order is the reverse of their capture order. Seeded any other way it passes by luck.

eng-test also answers `test_oracle` for this change; I am adding the concurrency-specific oracles, not replacing their view, and I expect the chair to merge both rather than pick one.
