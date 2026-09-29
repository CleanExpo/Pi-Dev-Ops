by: eng-concurrency
contributed: [eng-concurrency]
categories:
  concurrency:   {state: PRESCRIBED, ref: "#retry-without-a-dedup-key",      by: eng-concurrency, blocking: true}
  invariants:    {state: PRESCRIBED, ref: "#invariants-the-queue-must-hold", by: eng-concurrency, blocking: true}
  failure_modes: {state: PRESCRIBED, ref: "#retry-exhaustion-reports-synced", by: eng-concurrency, blocking: true}
  migration:     {state: N/A, reason: "003 changes only policies and grants, not row shape, so it opens no read-modify-write window against in-flight writers; if the runner is non-transactional the DROP/CREATE gap denies SELECT rather than leaking it — the fact that 003 was never applied at all is eng-release's, not mine"}
cross_domain:
  - "public.reports has no client-supplied natural key to dedupe on — eng-data owns whether that column and its unique index exist"
  - "getSyncStatus returns SYNCED while entries sit in status 'failed', so the only signal a technician sees is wrong — eng-observability owns the signal"
  - "no test in the repo ever calls drainQueue, so no interleaving oracle exists — eng-test owns the oracle; I name the two interleavings it must cover below"
  - "entry.endpoint is a free-form per-entry string and no server ingest route exists in this repo, so the receiving contract is unreviewable from here — eng-contract owns it"

## Retry without a dedup key

The spec's gate is `> Offline capture must survive poor connectivity and retry.` That states the goal and names no mechanism, so this is a prescription, not a decision.

Three separate paths produce the same duplicate today.

**1. The retry is not idempotent.** The POST carries no dedup key: `[VERIFIED]` `lib/sync-queue.ts:34` — `        method: "POST",` — with `headers: { "content-type": "application/json" }` and nothing else. A technician's phone POSTs a capture, the server commits it, the TLS connection drops before the response returns; `fetch` rejects, control lands in the `catch` at `lib/sync-queue.ts:40`, `incrementRetry` leaves the entry `pending`, and the next drain sends the identical body again. Nothing downstream can tell the two apart: `[VERIFIED]` `supabase/migrations/001_init.sql:2` — `  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),` — the primary key is server-generated, so both inserts get distinct ids and both survive. `grep -rniE "idempot|unique|for update|advisory"` over the fixture returns only `schema.prisma:3 email String @unique`; the same pattern does match `transaction` and `unique` elsewhere, so the zero hits for idempotency and locking are a real absence, not a broken query. `[VERIFIED]`

**2. Two drains race each other.** The read is a plain readonly transaction and each write is its own: `[VERIFIED]` `lib/sync-queue.ts:24` — `  const index = db.transaction("queue").objectStore("queue").index("status");` — and `lib/sync-queue.ts:25` — `  const entries: Entry[] = await getAll(index, "pending");`. Two triggers that both fire on reconnect (an `online` handler and a periodic or service-worker sync are the normal pair) each get the full pending set and each POSTs every entry, because nothing marks an entry in-flight between the read and the `removeEntry` at `lib/sync-queue.ts:39`. This is check-then-act with an `await fetch` sitting in the window. `[INFERENCE]` — I have watched this exact shape double-submit on the first reconnect after a tunnel, where reconnect fires two events milliseconds apart.

**3. The backoff is computed and then ignored.** `[VERIFIED]` `lib/sync-queue.ts:15` — `  const nextAttempt = Date.now() + RETRY_BACKOFF_MS[Math.min(entry.retryCount, 4)];` — is stored on the entry, but the selection at line 25 filters on `"pending"` only and never compares `nextAttemptAt` to now. The `// exponential backoff` comment at `lib/sync-queue.ts:2` describes a mechanism the code does not implement. A server returning 500 under load gets all five attempts back within one drain loop, at fetch speed.

Prescribe, in this order:

- A client-generated `client_entry_id` (uuid) minted at capture time, stored on the entry, sent as an `Idempotency-Key` header **and** persisted server-side under a unique constraint in the same transaction as the row insert — not after it. A key written after the side effect makes a crash in between do the work twice.
- A lease on drain: mark each entry `inflight` with an owner id and a timestamp inside a `readwrite` transaction *before* the `fetch`, and only that owner may clear it. If you use a TTL to reclaim a stalled lease, carry a fencing counter, otherwise a backgrounded tab wakes past the TTL and clears an entry a second drain is mid-flight on.
- Enforce the backoff: select `pending AND (nextAttemptAt IS NULL OR nextAttemptAt <= now)`.

I would drop all three if the ingest endpoint turns out to enforce a unique natural key server-side — that single constraint kills the whole class, and it is the cheapest thing to check. It is not checkable from this repo; the command is `\d+` on the ingest table in the target Postgres. `[UNCONFIRMED]`

## Invariants the queue must hold

Stated so they can be asserted rather than believed:

- **Exactly once per capture.** For any `client_entry_id`, `SELECT count(*) FROM <ingest table> WHERE client_entry_id = $1` is never greater than 1, no matter how many times `drainQueue` runs or how many drains overlap.
- **No entry is sent twice concurrently.** At any instant, at most one drain holds a given entry: an entry in `inflight` has exactly one owner id.
- **Order is preserved per subject, or order is explicitly irrelevant.** Today it is neither. `[VERIFIED]` `lib/sync-queue.ts:38` — `      if (!response.ok) await incrementRetry(db, entry);` — the loop then continues to the next entry. So for one inspection captured offline as create-then-amend, if the create returns 500 and the amend returns 200, the server sees the amend without the create. There is no head-of-line block and no sequence number; iteration order is whatever the `status` index yields, which is not capture order. Either add a monotonic per-subject sequence and stop the chain on first failure, or state in the spec that entries are independent and prove it — this is a decision nobody made.
- **A conflict is representable.** It currently is not: `[VERIFIED]` `lib/sync-queue.ts:7` — `  status: "pending" | "failed";` — while `lib/sync-queue.ts:48` reads `  const conflictCount = await count(db, "conflict");`. No code path writes `"conflict"`, so `SYNC_CONFLICT` at line 49 is unreachable and two technicians editing the same report offline resolve as last-writer-wins, silently. Add a version or `updated_at` precondition on the write and a real `conflict` terminal state, or delete the dead branch so nobody reads the code as if detection exists.

`[INFERENCE]` on ordering and conflict — greenfield mechanisms, nothing to cite; this is the shape in which offline queues fail once a second device touches the same subject.

## Retry exhaustion reports SYNCED

The three defects above compose into silent data loss, which is why I am claiming `failure_modes` alongside eng-failure rather than deferring it — I expect that seat to reach the same place from the other side, and the chair should record both.

Because the backoff is not enforced, a five-minute server outage burns all five attempts inside one drain. Then `[VERIFIED]` `lib/sync-queue.ts:28` — `    if (entry.retryCount >= MAX_RETRY_COUNT) {` — and `lib/sync-queue.ts:29` — `      await markFailed(db, entry.id);`. `drainQueue` only ever selects `"pending"`, so a `failed` entry is never retried by anything. And the status the technician sees is computed from `[VERIFIED]` `lib/sync-queue.ts:47` — `  const pendingCount = await count(db, "pending");` — plus the unreachable conflict count, so with the entry parked in `failed` both counters are zero and `lib/sync-queue.ts:51` returns `  return "SYNCED";`.

Concrete: technician captures readings in a basement, drives back into coverage during a deploy, the queue drains against a 502, all entries reach `failed` in under a second, the app shows synced, the phone is wiped or the job is closed. The readings are gone and nobody learns until an insurer asks for a report that has no data behind it.

Prescribe: `failed` must be a visible, drainable state — counted in `getSyncStatus` as its own value (not folded into `SYNCED`), retried by an operator- or user-triggered path, and never reachable while the entry has unexpired backoff remaining. Fix the backoff enforcement first; it is what turns a transient outage into a terminal one.

Where my instinct and the method disagreed: I would normally prescribe a durable server-side dedup table up front, but method 1 says the boring version gets tried first — a unique constraint on `client_entry_id` is the boring version and it does the same job, so that is what I prescribed.
