by: eng-concurrency
contributed: [eng-concurrency]
categories:
  concurrency:   {state: PRESCRIBED, ref: "#concurrent-drains-have-no-claim-step", by: eng-concurrency, blocking: true}
  invariants:    {state: PRESCRIBED, ref: "#one-queue-entry-must-produce-at-most-one-report", by: eng-concurrency, blocking: true}
  failure_modes: {state: PRESCRIBED, ref: "#backoff-is-written-but-never-read", by: eng-concurrency, blocking: true}
cross_domain:
  - "no test exercises two concurrent drains or a replayed POST; the only test is `classify` on one input — eng-test owns the oracle"
  - "`getSyncStatus` branches on a `\"conflict\"` status that the `Entry` union does not contain and no writer in this repo produces, so a second writer is assumed somewhere off-repo — eng-data owns who else writes this store"
  - "migration 003 is on disk but absent from APPLIED_LEDGER.txt, so the tenant policy that scopes report reads may not exist in prod — eng-release owns the ledger gap"

## Concurrent drains have no claim step

`drainQueue` selects work by status alone and never marks an entry as in-flight before the network call. [VERIFIED] `lib/sync-queue.ts:24-25`:

> `const index = db.transaction("queue").objectStore("queue").index("status");`
> `const entries: Entry[] = await getAll(index, "pending");`

The entry stays `"pending"` for the whole `await fetch(...)` window, and the only transitions out of `"pending"` happen *after* the response returns (`removeEntry`) or after it fails (`incrementRetry`, which spreads `...entry` and so leaves `status: "pending"` — `lib/sync-queue.ts:16-20`).

Concrete interleaving: IndexedDB is shared across every tab of the origin. Technician has the app open in two tabs (or a tab plus a service-worker sync handler). Both call `drainQueue`; both `getAll` returns the same pending entry E; both POST E's payload to `entry.endpoint`. The server receives two identical submissions. Neither drain can see the other's in-flight work because nothing in the store records it. No caller of `drainQueue` exists anywhere in the repo [VERIFIED] — `grep -rni drainQueue` over the fixture returns only the declaration at `lib/sync-queue.ts:23` — so the scheduling that determines how often this overlaps is an unmade decision, not a safe one.

Second interleaving, same cause: `incrementRetry` is a whole-record read-modify-write across two transactions. Both tabs read `retryCount: 2` at `getAll` time and both write `retryCount: 3` — one increment is lost, so an entry gets more than `MAX_RETRY_COUNT` attempts. Worse, the `put` writes back every field from the copy read minutes earlier, so any status another writer set in between (`markFailed`, or whatever sets the `"conflict"` state `getSyncStatus` reads) is resurrected to `"pending"`. [INFERENCE] on the interleaving, [VERIFIED] on the mechanism at `lib/sync-queue.ts:16`:

> `await put(db, {`

Prescription — grounded in the standard claim/lease shape for a client-side outbox:
1. Add an `"inflight"` status. In a single readwrite IndexedDB transaction, re-read the entry, assert it is still `"pending"`, flip it to `"inflight"` with an `attemptStartedAt`, and only then leave the transaction and issue the fetch. An entry already `"inflight"` is skipped by the other drain.
2. Reap `"inflight"` entries older than the fetch timeout back to `"pending"` at the top of each drain, so a killed tab does not strand work forever.
3. Make `incrementRetry` a re-read-then-write inside one readwrite transaction that touches `retryCount` and `nextAttemptAt` only, never a whole-record `put` of a stale copy.
4. Serialise drains within a tab with a single in-module promise, and across tabs with `navigator.locks.request("sync-drain", …)`. The Web Locks call is the cheap 80% fix; it does **not** replace steps 1–3, because a tab crash releases the lock while the POST is still in flight on the server.

## One queue entry must produce at most one report

The invariant nobody wrote down: **for a given `entry.id`, the server holds at most one report, no matter how many times that entry is delivered.** Nothing enforces it on either side.

Client side, the entry id is never transmitted. [VERIFIED] `lib/sync-queue.ts:33-37` sends the payload only:

> `body: JSON.stringify(entry.payload),`

There is no `Idempotency-Key` header and no dedupe token in the request. [VERIFIED] `grep -rni idempot` over the fixture returns nothing.

Server side, the receiving table cannot reject a duplicate either. [VERIFIED] `supabase/migrations/001_init.sql:2`:

> `  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),`

The primary key is server-generated per insert, so two deliveries of the same capture get two different ids and both persist. There is no unique constraint on any natural key in 001, 002 or 003 — the only `@unique` in the repo is `email` on `User` (`lib/schema.prisma:3`). This is the cheapest evidence available and it settles it: the whole duplicate class is live.

The failure needs no concurrency at all, which is why it will happen first: technician on bad connectivity POSTs, the server commits, the response is lost on the way back. `fetch` rejects, control lands in `catch { await incrementRetry(db, entry); }` (`lib/sync-queue.ts:40-42`), the entry stays pending, and the next drain sends it again. The insurer receives two reports for one site visit. Spec §2 asks for exactly this path to be safe — "Offline capture must survive poor connectivity and retry" — and states the goal without naming a mechanism, so this is unanswered, not decided.

Prescription — grounded in the standard at-least-once contract, since retry-on-network-error *is* at-least-once delivery whatever the comment calls it:
1. Send `entry.id` as an idempotency key on every POST (header or body field); it is already a stable client-generated uuid, so no new id source is needed.
2. Persist it: add `client_entry_id uuid` to `public.reports` with `UNIQUE (tenant_id, client_entry_id)`, and make the write an upsert on that constraint. The constraint, not application code, is what kills the race — a check-then-insert in the handler reopens it.
3. Have the endpoint return 200 with the existing report on a duplicate key, so the client's `response.ok` branch reaches `removeEntry` and the entry drains instead of retrying forever.
4. Backfill is not needed at zero rows; adding the column later, after real captures exist, means duplicates already in the table block the unique index. Cheaper now.

Testable form: `SELECT tenant_id, client_entry_id, count(*) FROM public.reports GROUP BY 1,2 HAVING count(*) > 1` returns zero rows, permanently.

## Backoff is written but never read

`incrementRetry` computes and stores a next-attempt time. [VERIFIED] `lib/sync-queue.ts:15`:

> `  const nextAttempt = Date.now() + RETRY_BACKOFF_MS[Math.min(entry.retryCount, 4)];`

Nothing ever reads it. [VERIFIED] `grep -rni nextAttemptAt` over the fixture returns exactly three hits — the type declaration at `lib/sync-queue.ts:9` and the two writes at `:9`/`:19` — and no read. `drainQueue`'s only selector is the status index (`lib/sync-queue.ts:24-25`), and the helper signature cannot express a time filter: `declare function getAll(i: IDBIndex, s: string): Promise<Entry[]>` (`lib/sync-queue.ts:55`). The comment on line 2 — `// exponential backoff` — describes an intent the code does not implement.

Concrete scenario, blast radius beyond the one entry: the report endpoint returns 503 during a deploy. Fifty technicians' queues drain. Every entry takes the `if (!response.ok) await incrementRetry(db, entry)` branch and stays `"pending"` with a `nextAttemptAt` nobody honours, so the very next drain — on whatever schedule ships, `online` event, interval, tab focus — re-sends all of them immediately at full rate against a server that is already failing. The 1s→30s ramp that was supposed to shed that load is inert. Then the second half: after five such passes, which under a fast drain trigger can elapse in seconds rather than the intended 48s, the guard at `lib/sync-queue.ts:28-30` fires —

> `    if (entry.retryCount >= MAX_RETRY_COUNT) {`

— and `markFailed` moves the entry to `"failed"`. `drainQueue` only ever selects `"pending"`, so a failed entry is never retried again by any code path in this file. A deploy blip of under a minute permanently strands a technician's offline captures, and the technician's only signal is `getSyncStatus` returning `"SYNCED"` — `pendingCount` is zero and `conflictCount` is zero, because failed entries are counted by neither (`lib/sync-queue.ts:46-52`). The system reports success over destroyed data.

Prescription — grounded in the ordinary shape of a durable outbox:
1. Filter on the clock at selection time: index on `nextAttemptAt` (or `[status, nextAttemptAt]`) and select entries whose `nextAttemptAt` is null or `<= Date.now()`. This requires widening the `getAll` helper past its current `(index, string)` signature.
2. Add jitter to each backoff step. Fifty clients whose queues all failed on the same 503 otherwise re-converge on the same retry instant and reproduce the thundering herd the backoff was meant to prevent.
3. `MAX_RETRY_COUNT` must bound elapsed time, not attempt count — retire an entry only once it is both out of attempts and older than a stated window (say 24h), so a short outage cannot exhaust the budget.
4. `"failed"` is currently terminal and invisible. Either make `getSyncStatus` surface it as a distinct non-`SYNCED` state or give the technician an explicit re-queue. Both, ideally — this is the only thing standing between a bad deploy and silent loss of field data.
5. Distinguish retryable from non-retryable responses. A 400 on a malformed payload is retried five times today and will never succeed; a 503 deserves every retry. `if (!response.ok)` treats them identically (`lib/sync-queue.ts:38`).
