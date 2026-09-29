by: eng-concurrency
contributed: [eng-concurrency]
categories:
  concurrency:   {state: PRESCRIBED, ref: "#concurrent-drains-and-retries-both-deliver-twice", by: eng-concurrency, blocking: true}
  failure_modes: {state: PRESCRIBED, ref: "#backoff-is-written-and-never-read", by: eng-concurrency, blocking: true}
  invariants:    {state: PRESCRIBED, ref: "#queue-invariants-nobody-stated", by: eng-concurrency}
  migration:     {state: DEFERRED,   reason: "IndexedDB entries outlive the app version that queued them; forced back before the first change to any queued payload shape or to entry.endpoint"}
cross_domain:
  - "public.reports has no column for the client's entry id and no natural-key unique constraint — eng-data owns whether the schema should carry one"
  - "getSyncStatus counts a \"conflict\" status that no code writes and the Entry union does not contain — eng-contract owns the dead union member"
  - "a technician seeing SYNCED while entries sit permanently failed is a detection gap as well as a correctness one — eng-observability owns the surfacing"

## Concurrent drains and retries both deliver twice

The spec asks for exactly this and names no mechanism:

> - Offline capture must survive poor connectivity and retry.

Surviving retry means the second delivery must be free. It is not. `[VERIFIED]` The entry's own identity never crosses the wire — `lib/sync-queue.ts:36` sends `        body: JSON.stringify(entry.payload),` and nothing else; there is no idempotency header on the request. `[VERIFIED]` The destination has no key to dedup on either: `supabase/migrations/001_init.sql:2` is `  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),` — the server mints a fresh row id per POST, so two POSTs of the same capture are two reports by construction. A repo-wide grep for `idempot|unique|ON CONFLICT|FOR UPDATE` returns one hit, `@unique` on `User.email`.

Three interleavings deliver twice, and all three are ordinary:

1. **Retry after a lost response.** `[VERIFIED]` `lib/sync-queue.ts:40-41` is `    } catch {` / `      await incrementRetry(db, entry);`. `catch` fires on timeout, abort, and connection reset — cases where the server received and committed the write and only the *response* was lost. The next drain re-POSTs work already done. This is the failure mode a technician on a bad cell tower produces most often.
2. **Two drains overlapping.** `[VERIFIED]` `lib/sync-queue.ts:24-25` reads `  const index = db.transaction("queue").objectStore("queue").index("status");` / `  const entries: Entry[] = await getAll(index, "pending");` — the read transaction closes immediately and the entry stays `"pending"` for the entire duration of the `await fetch`. Nothing claims the row. A second drain entering during a 10-second fetch reads the identical set and POSTs all of it again.
3. **`[VERIFIED]` Nothing in this repo says how many drains there are.** `grep -rn "drainQueue" .` across the fixture returns only the definition at `lib/sync-queue.ts:23`. Scheduling is undecided, which means it will be decided later by whoever wires an `online` listener, a service-worker `sync` handler and a poll timer — three callers, all firing within the same second on reconnect, is the normal outcome of that wiring, not a pathological one.

`[VERIFIED]` The same snapshot causes a lost update on the counter that is supposed to bound this. `lib/sync-queue.ts:15` computes from the stale read — `  const nextAttempt = Date.now() + RETRY_BACKOFF_MS[Math.min(entry.retryCount, 4)];` — and lines 16-20 `put` a whole reconstructed record `...entry`. Two drains both read `retryCount: 2` and both write `3`, so two failures advance the counter by one, and the write is a full-record clobber of anything else that touched the row meanwhile.

**Prescription.** Carry `entry.id` — a client-generated uuid that already exists on the record — as the idempotency key, and add a unique constraint on it server-side so the second insert fails rather than duplicating. My instinct here is a drain lock with a fencing token; `METHOD.md` §1 overrides it, because the boring version kills the whole class at the database and the lock only narrows interleaving (2) while leaving (1) untouched. Add the in-process claim second, as a cheap noise reduction, not as the correctness mechanism: mark `"in_flight"` in the same IndexedDB transaction that reads the entry, and reap stale in-flight entries on drain start.

**What would overturn this:** a POST handler that already upserts on a client-supplied key. I could not check it — the handler is not in this repo. `[UNCONFIRMED]` — `grep -rn "reports" app/api/` against the real service, and `\d+ public.reports` for a unique index on any column other than `id`.

## Backoff is written and never read

`[VERIFIED]` `nextAttemptAt` is written at `lib/sync-queue.ts:19` — `    nextAttemptAt: nextAttempt,` — and `grep -rn "nextAttemptAt" .` finds exactly three hits: the type at line 9, that write, and nothing else. `[VERIFIED]` The drain's only filter is status: `lib/sync-queue.ts:25`, `  const entries: Entry[] = await getAll(index, "pending");`. The comment at line 2, `// exponential backoff`, describes behaviour the code does not have.

The consequence is not a slow retry, it is a fast discard. `RETRY_BACKOFF_MS` sums to 48 seconds across five attempts, so the design intends an entry to survive roughly a minute of server trouble. Because the delay is never honoured, five *consecutive drain ticks* exhaust it instead. `[VERIFIED]` `lib/sync-queue.ts:28-30` then runs `      await markFailed(db, entry.id);` — and `markFailed` appears only there and in the declaration at line 56, so `"failed"` is terminal with no path back to `"pending"`.

Concrete scenario: the API returns 502 for 30 seconds during a routine deploy. A drain wired to a 5-second timer burns all five attempts in 25 seconds and permanently discards every queued capture on that technician's device. `[VERIFIED]` The technician is told it worked — `lib/sync-queue.ts:50-51` reads `  if (pendingCount > 0) return "PENDING_SYNC";` / `  return "SYNCED";`, and `"failed"` is counted by neither branch, so a device holding nothing but failed entries reports `SYNCED`. Against a server that is *down*, this is also a retry storm: every drain re-POSTs every pending entry with no delay at all.

**Prescription.** Filter the drain on `nextAttemptAt === null || nextAttemptAt <= Date.now()` — the field already exists, this is a one-line read. Add jitter to the backoff so a fleet of devices reconnecting after the same outage does not arrive in lockstep. Retry exhaustion must not be terminal-and-silent: either `"failed"` re-enters the queue on an explicit user action, or `getSyncStatus` must report it, because discarded field data that the UI calls `SYNCED` is unrecoverable. `[INFERENCE]` — the mechanism is a state machine with a write-only field; I have watched exactly this ship as "we have backoff" because the constant table was reviewed and the read path was not, which is `METHOD.md` §6 territory: the durable fix is a lint rule or a type that makes an unread scheduling field impossible, not this correction.

## Queue invariants nobody stated

None of these is written down anywhere in the repo, and each is a decision that was made silently. Stated as assertions a test can run against two concurrent drains over a seeded queue:

- **An accepted capture produces exactly one row in `public.reports`.** Currently false — see above. This is the one that matters; the others are its supporting conditions.
- **`retryCount` is monotonic and never loses an increment.** `[VERIFIED]` False under overlap, by the snapshot read at `lib/sync-queue.ts:25` feeding the reconstructing write at lines 16-20.
- **A `put` never overwrites a field the caller did not intend to change.** `[VERIFIED]` False — `incrementRetry` writes the whole record from an in-memory copy, so any concurrent edit to `payload` or `endpoint` between the `getAll` and the `put` is silently reverted.
- **The server's ordering of a technician's captures equals the order the technician made them.** `[VERIFIED]` False and undecidable: `Entry` at `lib/sync-queue.ts:5-12` has no capture timestamp or sequence at all, `getAll` on the `status` index yields entries in primary-key order rather than capture order, and `supabase/migrations/001_init.sql:5` records `  created_at timestamptz NOT NULL DEFAULT now()` — arrival time on the server. Retries reorder arrival by minutes. If any report or classification depends on reading sequence, it is reading a shuffle. `[INFERENCE]` — a captured-at column plus ordering on it is the fix, but the decision to make first is whether order is load-bearing at all; nothing in `spec.md` says.

**Prescription.** Write these four into the module as executable assertions, not comments. The oracle that makes them real is a two-drain interleaving test — `eng-test` owns its construction; my requirement on it is that it must fail today, and that the assertion counting rows after a forced response-loss must be the first one written.

## Migration

`DEFERRED`. The IndexedDB queue is a durable store that survives app deploys, so entries serialised by version N drain into version N+1's endpoint. `[VERIFIED]` `Entry` at `lib/sync-queue.ts:5-12` carries no schema version, and `lib/sync-queue.ts:33` posts to `entry.endpoint` — a URL frozen at capture time, which will outlive the route that answers it. Nothing forces this now because no payload shape has changed yet. The condition that forces it back: **the first change to any queued payload shape, or to `entry.endpoint`** — at that moment every device holding old entries needs either a version tag to migrate on or an explicit drop rule, and neither exists.
