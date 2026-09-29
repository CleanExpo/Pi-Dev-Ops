by: eng-concurrency
contributed: [eng-concurrency]
categories:
  concurrency:   {state: PRESCRIBED, ref: "#duplicate-submission-on-overlapping-drains", by: eng-concurrency, blocking: true}
  failure_modes: {state: PRESCRIBED, ref: "#backoff-that-never-delays", by: eng-concurrency, blocking: true}
  invariants:    {state: PRESCRIBED, ref: "#queue-entry-invariants", by: eng-concurrency, blocking: true}
cross_domain:
  - "003_rls_fix.sql exists but APPLIED_LEDGER.txt records only 001 and 002, so the permissive policy is what is live — eng-release owns the ledger gap and eng-authz owns the policy"
  - "__tests__/engine.test.ts covers one of three classify branches and nothing exercises drainQueue at all — eng-test owns the oracle for the interleavings below"
  - "runWatchdog returns alerted:false silently when ALERT_EMAIL is unset and sendEmail never throws, so a failed drain has no path to a human — eng-observability owns that"

## Duplicate submission on overlapping drains

`drainQueue` is a check-then-act across an `await`, with nothing marking an entry as in-flight and nothing on the wire letting the server recognise a repeat.

The read happens once, in a transaction that is dead by the first await:

> `const entries: Entry[] = await getAll(index, "pending");` — `lib/sync-queue.ts:25` [VERIFIED]

The entry then stays `pending` for the entire duration of the network call, and is only removed after it returns:

> `if (!response.ok) await incrementRetry(db, entry);` / `else await removeEntry(db, entry.id);` — `lib/sync-queue.ts:38-39` [VERIFIED]

Concrete interleaving: a technician regains signal in a carpark. The `online` event fires a drain; two seconds later the service worker's `sync` event fires a second drain while the first is still awaiting a POST that is stalled behind a 30-second edge timeout. The second drain's `getAll(index, "pending")` returns the same entry — it was never taken out of `pending` — and POSTs it again. Both eventually succeed. Two reports exist for one inspection. `removeEntry` runs twice on the same id, the second harmlessly, so nothing in the client ever indicates it happened. [INFERENCE] — this is the standard shape of the queue-drained-twice bug; the mechanism is that IndexedDB transactions auto-close at the first microtask boundary, so the read and the write are unavoidably separate transactions here.

The server cannot dedup it either. The POST carries no idempotency key:

> `headers: { "content-type": "application/json" },` — `lib/sync-queue.ts:35` [VERIFIED]

and the only uniqueness on the destination table is a server-minted surrogate, which is a different value on every insert by construction:

> `id uuid PRIMARY KEY DEFAULT gen_random_uuid(),` — `supabase/migrations/001_init.sql:2` [VERIFIED]

I grepped the whole fixture for a lock, a mutex, an in-flight flag or an idempotency header and there is none: `grep -rn "drainQueue\|idempot\|lock" .` returns only the declaration site and the two `nextAttemptAt` lines. [VERIFIED]

**Prescription.** Three things, in this order of value:

1. Send `entry.id` as an `Idempotency-Key` header (or as a client-generated `client_entry_id` in the body) and put a unique constraint on it server-side, scoped by `tenant_id`. This is the only mechanism that survives the case the client cannot see — the POST that reached the server, wrote the row, and then failed on the response. Retrying that entry is *correct* behaviour and will always happen; the constraint is what makes it harmless. Grounded in: at-least-once delivery cannot be removed from an offline client, so the duplicate must be absorbed at the write, not prevented at the send.
2. Add a `sending` status and transition `pending → sending` in its own write *before* the fetch, and have `getAll` select only `pending`. This narrows the window but does not close it — a tab killed mid-flight leaves the entry stranded in `sending`, so it needs a lease timestamp and a sweeper that returns stale `sending` rows to `pending`. That sweeper is exactly why item 1 is not optional: a returned entry gets re-sent by design.
3. Guard `drainQueue` against re-entry within a single JS context with a module-level promise (`if (inFlight) return inFlight`). Cheap, but note it does nothing across a document and its service worker, which are separate contexts — do not let it be mistaken for the fix.

The spec's gate here is `> Offline capture must survive poor connectivity and retry.` I read "survive" as including "does not duplicate", and nothing in the spec says which of duplicate-vs-drop is the acceptable failure. That is a decision being made silently by the code, and it currently chooses duplicate.

## Backoff that never delays

`nextAttemptAt` is computed, written, and never read. This is verified by exhaustive grep — the identifier appears exactly three times in the repository, all of them writes or the type declaration, and none in `drainQueue`:

> `lib/sync-queue.ts:9: nextAttemptAt: number | null;`
> `lib/sync-queue.ts:19: nextAttemptAt: nextAttempt,`
> — and no third occurrence [VERIFIED]

`drainQueue` selects on status alone (`lib/sync-queue.ts:25`, quoted above) and never compares against the clock. So the comment is false:

> `const RETRY_BACKOFF_MS = [1000, 2000, 5000, 10000, 30000]; // exponential backoff` — `lib/sync-queue.ts:2` [VERIFIED]

Two consequences, both of which will happen on the first server-side incident:

**Premature dead-lettering.** The retry ladder is supposed to spend 48 seconds before giving up. With the delay unenforced, a drain triggered on a 1-second interval — or, worse, a loop that a caller fires on every `online`/`visibilitychange` — burns all five attempts in well under a second:

> `if (entry.retryCount >= MAX_RETRY_COUNT) { await markFailed(db, entry.id); continue; }` — `lib/sync-queue.ts:28-30` [VERIFIED]

A 30-second 502 from a deploy rollout is enough to permanently fail every queued capture on every technician's device. The readings are then in a `failed` status with, as far as I can see in this repo, no requeue path at all — `markFailed` is a one-way door and nothing reads `failed` back.

**Retry storm.** The delay is the only thing spacing requests. Without it, when connectivity returns to a site with a hundred technicians, every device drains its full backlog as fast as `fetch` will accept it, against a server that is by hypothesis already unhealthy. [INFERENCE] — this is the thundering herd at reconnection; the backoff array is the mitigation the author already reached for and then did not wire up.

**Prescription.** Filter the drain on the clock — `entries.filter(e => (e.nextAttemptAt ?? 0) <= Date.now())` at minimum, better as a compound IndexedDB index on `[status, nextAttemptAt]` so the delayed entries are not even read. Add full jitter to the ladder (`random() * backoff[n]`) before the fleet-wide reconnection case, not after: without jitter, a hundred devices that lost signal to the same tower retry in lockstep and the ladder just moves the spike rather than flattening it. Grounded in AWS's exponential-backoff-and-jitter result, which is the standard reference for why the un-jittered ladder does not help here.

## Queue entry invariants

Three assertions that should hold and currently do not. Each is testable against a fake IDB with two interleaved drains, which is the test I would write before any of the fixes above.

**`retryCount` must be monotonic.** `incrementRetry` writes back a value derived from a snapshot read before the network call:

> `retryCount: entry.retryCount + 1,` — `lib/sync-queue.ts:18` [VERIFIED]

Two overlapping drains both read `retryCount: 2`, both fail, both write `3`. Two failures, one increment. `MAX_RETRY_COUNT` is therefore not a bound on attempts — it is a bound on *observed* attempts, and the two diverge exactly when the system is under the load that makes the bound matter. [INFERENCE] — classic read-modify-write lost update; the same shape as `SELECT balance; balance += x; UPDATE`.

**An entry that has been dead-lettered must never be sent again.** `incrementRetry` does a whole-record `put` from the stale snapshot:

> `await put(db, { ...entry, ...` — `lib/sync-queue.ts:16` [VERIFIED]

`...entry` carries the `status` field the drain read minutes earlier. Interleaving: drain A reads the entry at `retryCount: 4` and starts a slow POST. Drain B reads the same entry, sees `retryCount >= MAX_RETRY_COUNT`, calls `markFailed`, status becomes `failed`. Drain A's POST times out, `incrementRetry` fires, and `{...entry}` writes `status: "pending"` back over it. The entry is resurrected into the drain set with a fresh `nextAttemptAt` and rides again. The narrow fix is to stop spreading the whole record and write only the two fields that changed; the correct fix is a read-modify-write inside a single `readwrite` transaction that re-reads the current record rather than trusting the snapshot.

**`getSyncStatus` must never report `SYNCED` while unsynced or conflicting work exists.** It cannot currently report a conflict at all, because it counts a status that the type says does not exist:

> `const conflictCount = await count(db, "conflict");` — `lib/sync-queue.ts:48` [VERIFIED]

against

> `status: "pending" | "failed";` — `lib/sync-queue.ts:6` [VERIFIED]

Nothing in this repo writes `"conflict"` — grep returns only lines 48 and 49. So `conflictCount` is always `0` and `SYNC_CONFLICT` is unreachable dead code. [VERIFIED]

That matters beyond the dead branch, because it is the visible symptom of a missing mechanism: there is no version, no `updated_at`, and no ETag on the entry or on `public.reports` (`001_init.sql` has `id`, `tenant_id`, `body`, `created_at` and nothing else) [VERIFIED]. Two technicians capturing against the same inspection offline, both draining, means the second `body` silently replaces the first with no record that the first existed. The UI reports `SYNCED`. This intersects the spec's distribution gate — `> A report may not be distributed unless its verification checklist is complete.` — because if the checklist lives inside `body`, a stale overwrite landing after the gate check reverts a complete checklist on an already-distributed report and no code path notices.

**Prescription.** Decide last-write-wins explicitly or add a version. If last-write-wins is acceptable, delete the `conflict` branch so the status enum tells the truth. If it is not, carry a `version` (or the server's `updated_at`) on the entry, have the server reject a write whose base version is stale with `409`, and have `drainQueue` map `409` to a `conflict` status rather than to `incrementRetry` — note that today a `409` is `!response.ok` and therefore goes down the retry path, which will retry a conflict five times and then dead-letter it. Either answer is defensible; having neither, while shipping an unreachable `SYNC_CONFLICT` constant that implies the second, is the silent decision.
