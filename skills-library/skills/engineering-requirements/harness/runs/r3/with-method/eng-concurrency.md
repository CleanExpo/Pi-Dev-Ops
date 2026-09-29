by: eng-concurrency
contributed: [eng-concurrency]
categories:
  concurrency:  {state: PRESCRIBED, ref: "#concurrency",  by: eng-concurrency, blocking: true}
  invariants:   {state: PRESCRIBED, ref: "#invariants",   by: eng-concurrency, blocking: true}
  test_oracle:  {state: PRESCRIBED, ref: "#test-oracle",  by: eng-concurrency}
cross_domain:
  - "002_policies.sql grants anon SELECT/INSERT/UPDATE/DELETE on reports and 003 only REVOKEs it — eng-authz owns whether the revoke is sufficient"
  - "APPLIED_LEDGER.txt lists 001 and 002 but not 003, so the tenant policy may not exist in the environment the queue POSTs into — eng-release owns the ledger/directory disagreement"
  - "sendEmail swallows every failure and runWatchdog returns alerted:true on a dropped mail — eng-observability owns whether that is a detectable path"

## Concurrency

The spec says offline capture "must survive poor connectivity and retry". The drain loop retries, but nothing in the system distinguishes a retry from a new capture. Four concrete interleavings, all reachable today:

**1. Lost response duplicates the report.** The technician's phone POSTs, the server commits the row, the connection drops before the response arrives. `fetch` rejects, the `catch` runs `incrementRetry`, and the identical payload is POSTed again on the next drain. `removeEntry` is only reached on a 2xx that was actually received — `[VERIFIED]` `lib/sync-queue.ts:38-42`, `> if (!response.ok) await incrementRetry(db, entry);` / `> else await removeEntry(db, entry.id);` / `> } catch { await incrementRetry(db, entry); }`. The entry already carries a durable client-side identity — `> id: string;` at `lib/sync-queue.ts:6` — and it is used only for local deletion, never sent to the server. Nothing in the fixture references an idempotency key: `grep -rn "idempot\|Idempot" .` over the fixture returns nothing `[VERIFIED]`.

*Prescription:* send `entry.id` as an `Idempotency-Key` header (or a `client_entry_id` column in the body), and have the write endpoint upsert on it inside the same transaction as the row insert — not after it. Storing the key after the side effect reproduces the same bug one layer down.

**2. Two drains, one queue, doubled traffic and a lost retry count.** `getAll` reads the pending set through a transaction that is created and left on line 24, then the loop awaits network I/O for each entry — the IndexedDB transaction has auto-committed long before the first `fetch` resolves `[VERIFIED]` `lib/sync-queue.ts:24-25`, `> const index = db.transaction("queue").objectStore("queue").index("status");`. `entries` is therefore a stale snapshot with no lock held. Two tabs, or a tab plus a service-worker sync event, both snapshot the same pending rows and both POST them. Worse, `incrementRetry` is a read-modify-write off that stale object — `> retryCount: entry.retryCount + 1` at `lib/sync-queue.ts:19` — so two concurrent drains of an entry at `retryCount: 2` both write `3`, and the entry gets more attempts than `MAX_RETRY_COUNT` allows. No `navigator.locks`, mutex, or in-flight guard exists anywhere in the file `[VERIFIED]` (grep for `lock` over the fixture returns only the `lib/sync-queue.ts:24` transaction line).

*Prescription:* wrap the whole drain in `navigator.locks.request("sync-queue", ...)` so only one drain runs per origin, and make `incrementRetry` re-read the entry inside a `readwrite` transaction rather than writing back a snapshot captured before the network call.

**3. The backoff is computed, stored, and never consulted.** `nextAttemptAt` is written on every failure and read by nothing — the only two occurrences in the repo are the type declaration and the write `[VERIFIED]` `lib/sync-queue.ts:9` `> nextAttemptAt: number | null;` and `lib/sync-queue.ts:19` `> nextAttemptAt: nextAttempt,`; grep across the fixture finds no third. The drain selects purely on status `[VERIFIED]` `lib/sync-queue.ts:25` `> const entries: Entry[] = await getAll(index, "pending");`. So the comment on line 2 describing exponential backoff is aspirational: a whole crew reconnecting after a site visit burns all five attempts against a struggling server in whatever interval fires the drain, which is the standard retry-storm shape — the server is slow, so everyone retries, so the server is slower `[INFERENCE]`.

*Prescription:* filter the drain to `nextAttemptAt == null || nextAttemptAt <= Date.now()`, and add jitter to `RETRY_BACKOFF_MS` so a fleet that lost connectivity together does not return in lockstep.

**4. Capture order is not preserved, and the conflict state is unreachable.** The loop applies entries in the order `getAll` returns them — index key order on `status`, with ties broken by the primary key, which is a random uuid `[INFERENCE]`, the mechanism being that IndexedDB orders index results by index key then primary key. Two edits to the same inspection captured five minutes apart can therefore be POSTed in reverse order, and the server has no sequence number to reject the stale one: `Entry` carries no version, ETag, or capture timestamp `[VERIFIED]` `lib/sync-queue.ts:5-12`. Meanwhile `getSyncStatus` counts a `"conflict"` bucket `[VERIFIED]` `lib/sync-queue.ts:48` `> const conflictCount = await count(db, "conflict");` that no code path can ever produce — `Entry.status` is typed `> status: "pending" | "failed";` `[VERIFIED]` `lib/sync-queue.ts:7`. So the silent decision is last-arrival-wins, and the UI has a state for a conflict-detection mechanism nobody built.

*Prescription:* add a monotonic `capturedSeq` per device to `Entry`, drain in `capturedSeq` order, and have the server reject an out-of-order write for a row it has already advanced past — writing the entry to `"conflict"` so the existing status branch becomes reachable. If last-write-wins is the intended answer, say so in the spec and delete the `SYNC_CONFLICT` branch; an unreachable state is a lie the next reader will believe.

Per method §2, the observation that overturns all of this: if the write endpoint is genuinely a pure upsert keyed on something already inside `payload`, findings 1 and 4 collapse to documentation. I could not check the endpoint — the fixture contains only `app/api/health/route.ts` `[UNCONFIRMED]`; the command is `rg -l "reports" app/api` against the real application.

## Invariants

State it as the assertion: **for any client entry id, at most one `public.reports` row exists, no matter how many times it was POSTed.** Right now nothing enforces it at any layer. The table has a surrogate primary key and no unique constraint on any natural key `[VERIFIED]` `supabase/migrations/001_init.sql:1-6`, `> id uuid PRIMARY KEY DEFAULT gen_random_uuid(),` — every retry inserts a fresh uuid and succeeds. There is no `ON CONFLICT` clause anywhere in the migrations directory `[VERIFIED]` (grep over the fixture returns no match).

This is the cheapest possible kill for the entire race class in finding 1: a `client_entry_id uuid NOT NULL UNIQUE` column on `public.reports` makes a duplicate insert fail loudly at the database rather than surface weeks later as two invoices to the same insurer. Application-level "check if it exists, then insert" does not substitute — that is the check-then-act pattern the constraint exists to make impossible.

Second invariant, weaker but testable: **no entry is attempted more than `MAX_RETRY_COUNT` times.** Finding 2 breaks it under concurrent drains; the constraint that restores it is the single-drain lock plus re-reading `retryCount` inside the write transaction.

Grounding: both are the standard resolution for at-least-once delivery into a relational store; a unique constraint on the dedup key is the only mechanism that holds when the application layer is running in two processes.

## Test oracle

The only test in the repo asserts one branch of a pure function `[VERIFIED]` `__tests__/engine.test.ts:5-7`, `> it("returns category 3 for sewage", () => {`. Nothing exercises `drainQueue` at all, so every failure above ships green. The spec's "Tests gate the classification engine" is satisfied for the engine and silent about the queue, which is where the concurrency risk actually lives.

Three tests that would fail today:

1. **Duplicate suppression.** Stub `fetch` to commit server-side and then throw (simulating a lost response). Drain twice. Assert the server received the work once, or that the second POST carried the same idempotency key and was rejected. This fails now because no key is sent.
2. **Concurrent drain.** Seed one pending entry, call `drainQueue(db)` twice without awaiting the first, with a `fetch` stub that resolves after a tick. Assert exactly one POST, and that a failing entry ends at `retryCount: 1` and not `retryCount: 1` written twice. This fails now because there is no lock and `incrementRetry` writes back a stale snapshot.
3. **Backoff is honoured.** Fail an entry, then drain again immediately with a frozen clock. Assert zero POSTs because `nextAttemptAt` is in the future. This fails now because `nextAttemptAt` is never read.

Note for the chair: eng-test also answers this category and should own the general oracle question; my claim here is scoped to the three interleavings above, which need a fake timer and a controllable `fetch` and will not appear on a general test-coverage list.
