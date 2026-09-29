by: eng-concurrency
categories:
  concurrency: {state: PRESCRIBED, ref: "#concurrency", by: eng-concurrency, blocking: true}
cross_domain:
  - "public.reports has no unique key on any client-supplied identifier (001_init.sql:2, `id uuid PRIMARY KEY DEFAULT gen_random_uuid()`) — eng-data owns whether the dedup key belongs in the schema"
  - "runWatchdog re-sends the alert email on every invocation with no suppression key (notify.ts:26-28) — eng-observability owns alert-storm policy"
  - "003_rls_fix.sql is absent from supabase/APPLIED_LEDGER.txt, so the permissive 002 policy is what is live — eng-release owns the ledger/directory disagreement"
  - "entries that exhaust MAX_RETRY_COUNT are markFailed'd with no operator path back (sync-queue.ts:28-30) — eng-failure owns the terminal state"

## concurrency

The spec states the gate but not the mechanism:

> Offline capture must survive poor connectivity and retry.

"Survive retry" is the requirement. Nothing in `lib/sync-queue.ts` makes a retry safe to repeat, and the server table it retries into cannot reject a repeat. Three distinct interleavings, all reachable today.

**Where the method overrode my instinct:** my first reach was a per-device drain lock plus a fencing token. Method §1 says the boring version carries the burden only if it loses — a unique constraint on a client-generated entry id with `ON CONFLICT DO NOTHING` kills this entire race class with no lock, no TTL, and no stall-past-expiry failure. The lock is unjustified until the constraint is measured and found insufficient.

### 1. The retry is not idempotent, and the sink cannot deduplicate it

`drainQueue` POSTs the payload, then deletes the entry as a separate step:

> `const response = await fetch(entry.endpoint, {` — `lib/sync-queue.ts:33` [VERIFIED]
> `if (!response.ok) await incrementRetry(db, entry);` / `else await removeEntry(db, entry.id);` — `lib/sync-queue.ts:38-39` [VERIFIED]

Concrete scenario: a technician on a train POSTs one inspection; the server commits it and begins the response; the tunnel drops before the response lands. `fetch` rejects, control reaches the `catch` at line 40, `incrementRetry` runs, and the same payload is POSTed again on the next drain. The same thing happens if the tab is closed or the browser evicts the page between line 33 returning 200 and `removeEntry` at line 39 completing — the delete is outside the delivery. This is at-least-once delivery described in the code as if it were exactly-once.

Nothing downstream absorbs the duplicate. The report table's only key is a server-generated UUID:

> `id uuid PRIMARY KEY DEFAULT gen_random_uuid(),` — `supabase/migrations/001_init.sql:2` [VERIFIED]

There is no unique constraint anywhere on the ingest path — the only `@unique` in the repo is `User.email` [VERIFIED, `lib/schema.prisma:3`: `email       String       @unique`], and no `ON CONFLICT` clause exists in any migration [VERIFIED, grep over `supabase/` returns no match]. So the second POST inserts a second row, and per the spec that row is a second report distributed to an insurer. [INFERENCE] on the distribution consequence — I have seen this exact shape produce duplicate customer-facing artifacts twice, both discovered in reconciliation weeks later, because a duplicate insert raises no error.

**Prescribed:** every `Entry` carries a client-generated UUID minted at capture time, sent as both an `Idempotency-Key` header and a column; `public.reports` gets `UNIQUE (tenant_id, client_entry_id)` and the ingest writes `INSERT ... ON CONFLICT (tenant_id, client_entry_id) DO NOTHING RETURNING id`; a conflict returns 200 so the client deletes the entry rather than retrying forever. Grounded in the constraint being the only mechanism that holds when the client crashes between the call and the bookkeeping — client-side ordering cannot, because the client is the thing that died.

### 2. Two drains interleave on a stale snapshot and silently overwrite each other

The entry list is read in a transaction that has already closed by the time the writes happen, and every write is a whole-record blind overwrite of that stale snapshot:

> `const index = db.transaction("queue").objectStore("queue").index("status");` — `lib/sync-queue.ts:24` [VERIFIED]
> `await put(db, { ...entry, retryCount: entry.retryCount + 1, nextAttemptAt: nextAttempt });` — `lib/sync-queue.ts:16-20` [VERIFIED]

`drainQueue` is `export`ed and has no in-flight guard, no lock, and no caller in this repo [VERIFIED: grep for `drainQueue` returns only its own definition at line 23]. Concrete scenario: a reconnect handler and a visibility-change handler both fire when the technician's phone leaves airplane mode. Both call `getAll(index, "pending")` and both receive entry `E` with `retryCount: 0`. Both POST it (finding 1). Both then run `incrementRetry` computing `0 + 1`, and both `put` `retryCount: 1`. Two real network attempts are recorded as one, so `MAX_RETRY_COUNT` counts attempts at roughly half rate — a permanently rejecting endpoint gets ten POSTs, not five. The `{...entry}` spread also restores every other field from the snapshot, so if a second writer changed `status` between the `getAll` and the `put`, that change is erased.

This is read-modify-write across a closed transaction, which is the same defect as `SELECT balance; balance += x; UPDATE` and fails for the same reason.

**Prescribed:** `drainQueue` takes a module-level in-flight promise so a second concurrent call joins the first rather than starting a second pass, and `incrementRetry` re-reads the entry inside a `readwrite` transaction that also writes it, mutating only `retryCount` and `nextAttemptAt` rather than `put`-ing a whole snapshot. The in-flight guard is per-tab and does not cover two tabs — the constraint from finding 1 is what covers that, which is why it is the blocking half.

### 3. The backoff is write-only: `nextAttemptAt` is computed, stored, and never read

> `nextAttemptAt: number | null;` — `lib/sync-queue.ts:9` [VERIFIED]
> `nextAttemptAt: nextAttempt,` — `lib/sync-queue.ts:19` [VERIFIED]

Those are the only two occurrences in the repository [VERIFIED: `grep -rn nextAttemptAt .` returns exactly lines 9 and 19]. The drain loop selects on the status index alone and gates only on the retry count:

> `if (entry.retryCount >= MAX_RETRY_COUNT) {` — `lib/sync-queue.ts:28` [VERIFIED]

So the comment at line 2 — `// exponential backoff` — describes a mechanism that does not exist. Concrete scenario: the ingest endpoint returns 503 during a deploy. Whatever schedule calls `drainQueue` (a 30-second timer, an online event, a retry loop) re-POSTs every pending entry on every tick with no delay, because the 1s/2s/5s/10s/30s ladder is never consulted. The five-attempt budget is consumed inside two and a half minutes rather than the ~48 seconds of intended spacing plus scheduler interval, and every offline device in the field does this in step — the ladder is pure `Date.now() + constant` with no jitter, so devices that queued during the same outage retry at the same instants. That is a client-driven thundering herd aimed at an endpoint that just told everyone it was unhealthy.

**Prescribed:** the drain filter becomes `status === "pending" && (nextAttemptAt === null || nextAttemptAt <= Date.now())`, and the delay gets full jitter (`random() * backoff[n]`) so a shared outage does not produce a synchronised retry wave. Grounded in the ladder already being computed — the fix is to read it, not to design it.

### 4. `SYNC_CONFLICT` is unreachable, so concurrent edits resolve as last-write-wins in silence

> `const conflictCount = await count(db, "conflict");` / `if (conflictCount > 0) return "SYNC_CONFLICT";` — `lib/sync-queue.ts:48-49` [VERIFIED]

The status union admits no such value:

> `status: "pending" | "failed";` — `lib/sync-queue.ts:7` [VERIFIED]

No code in the repo writes `"conflict"` [VERIFIED: the only matches for `conflict` are lines 48 and 49, both readers]. Concrete scenario: two technicians capture readings for the same site offline, or one technician captures on a phone and a tablet; both queues drain; both writes land; the later arrival wins and the UI reports `SYNCED`. Nobody is told a reading was overwritten. The branch that would have told them cannot fire, and TypeScript will not flag it because `count` takes `s: string` [VERIFIED, `lib/sync-queue.ts:58`: `declare function count(db: IDBDatabase, s: string): Promise<number>;`] — Method §8, a boundary typed as `string` moved this from a compile error to a permanent silent no-op.

Note also that ordering here cannot come from arrival time: entries drain in whatever order `getAll` returns from devices whose clocks are independent, so "later" is not knowable from the client.

**Prescribed:** either add `"conflict"` to the union, narrow `count`'s parameter to `Entry["status"] | "conflict"` so the compiler proves the state is reachable, and define the writer — the ingest returns 409 with the server's current version and the client marks the entry `"conflict"`; or delete lines 48-49 and state in the spec that last-write-wins is the accepted resolution. What is not acceptable is shipping dead conflict-detection that reads as a working guarantee. **This decision must be made explicitly** — it is currently a decision made by omission.

### What would overturn all four

If `drainQueue` is only ever invoked from a single service-worker `sync` event, which the platform already serialises, findings 2 and 3 shrink to the herd argument alone. That is checkable and I could not check it from here: no caller exists in this repository. [UNCONFIRMED] — the command is `grep -rn "drainQueue" <app-repo>` against whatever registers the scheduler. Finding 1 survives either way, because it is a crash between two steps on one caller, not a race between two.
