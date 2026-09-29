by: eng-failure
contributed: [eng-failure]
categories:
  failure_modes:  {state: PRESCRIBED, ref: "#silent-data-loss-when-the-queue-gives-up", by: eng-failure, blocking: true}
  observability:  {state: PRESCRIBED, ref: "#the-watchdog-cannot-report-its-own-failure", by: eng-failure, blocking: true}
cross_domain:
  - "003_rls_fix.sql is in migrations/ but not in APPLIED_LEDGER.txt, so the live policy is still 002's `FOR SELECT USING (true)` with anon granted SELECT — eng-release owns the ledger gap, eng-authz owns the cross-tenant read"
  - "vitest.config.ts includes only `lib/**/__tests__/**` and `app/**/__tests__/**`, so `__tests__/engine.test.ts` at repo root is never collected and the suite is green on zero tests — eng-test owns it"
  - "app/api/health/route.ts returns `status: \"ok\"` unconditionally and probes nothing, so a load balancer keeps routing to a process whose DB is gone — eng-observability owns the liveness-vs-readiness split"
  - "a successful POST followed by a failing removeEntry re-POSTs the same reading on the next drain; there is no idempotency key on the payload — eng-concurrency owns duplicate-write semantics"
  - "spec gate 'a report may not be distributed unless its verification checklist is complete' has no checklist column in `public.reports` (id, tenant_id, body, created_at) and no distribution code path — eng-data owns whether that state is even persisted"

## Silent data loss when the queue gives up

The offline queue's terminal state is invisible to the only function that reports sync health, so the failure mode is not "sync broke" — it is "the technician is told everything is fine while the readings are stranded on the handset."

The concrete run: a technician captures 20 readings in a basement. The site's uplink is degraded (server returning 502, or captive portal). `drainQueue` walks the pending set and each non-ok response increments `retryCount`. The entire backoff ladder is `1000 + 2000 + 5000 + 10000 + 30000` — **48 seconds of total tolerance** — after which `retryCount >= 5` and every entry is moved to `failed`.

`[VERIFIED]` `lib/sync-queue.ts:2` — `const RETRY_BACKOFF_MS = [1000, 2000, 5000, 10000, 30000]; // exponential backoff`
`[VERIFIED]` `lib/sync-queue.ts:28-29` — `if (entry.retryCount >= MAX_RETRY_COUNT) {` / `await markFailed(db, entry.id);`

`getSyncStatus` then counts `"pending"` and `"conflict"`, and `failed` is neither:

`[VERIFIED]` `lib/sync-queue.ts:47-51` — `const pendingCount = await count(db, "pending");` / `const conflictCount = await count(db, "conflict");` / `if (conflictCount > 0) return "SYNC_CONFLICT";` / `if (pendingCount > 0) return "PENDING_SYNC";` / `return "SYNCED";`

So the moment the last entry is marked failed, `pendingCount` drops to 0 and the device reports `SYNCED`. The technician leaves the site. Nothing on the server knows the readings existed. Nobody notices — ever — because the only signal was the device's own status string, and it says success. This is the classic fail-open-into-wrongness: the fallback returns the *reassuring* value rather than the *safe* one.

Three compounding defects in the same function:

1. **`markFailed` is terminal with no re-queue path.** `drainQueue` reads only `getAll(index, "pending")` (`lib/sync-queue.ts:25` — `const entries: Entry[] = await getAll(index, "pending");`). Nothing in this file moves an entry from `failed` back to `pending`. When the server recovers 10 minutes later, the failed entries are not retried. A 48-second outage causes permanent loss, not delayed delivery. That directly contradicts spec §2: "Offline capture must survive poor connectivity and retry."

2. **`SYNC_CONFLICT` is unreachable.** The `Entry` type admits only two statuses — `[VERIFIED]` `lib/sync-queue.ts:7` — `status: "pending" | "failed";` — so `count(db, "conflict")` is structurally always 0 and the first branch of `getSyncStatus` is dead. Whoever wrote the status ladder believed conflicts were being surfaced. They are not. `[INFERENCE]` — I have seen this exact shape ship twice: a status enum narrowed in a later refactor while the consumer's string literals were left behind, and the branch silently becomes unreachable rather than a type error, because `count()` takes a bare `string`.

3. **No timeout on the outbound fetch.** `[VERIFIED]` `lib/sync-queue.ts:33-37` — `const response = await fetch(entry.endpoint, {` … with no `signal`. Compare `lib/notify.ts:15` — `signal: AbortSignal.timeout(10_000),` — the notify path was given a timeout and this one was not, which is the tell that it was an oversight rather than a decision. A captive portal or a half-open TCP connection (very common on the cellular-to-wifi handoff this queue exists to survive) accepts the connection and never responds. `await fetch` never settles, the sequential `for` loop never reaches entry 2, `retryCount` never increments, and the queue is wedged in `PENDING_SYNC` indefinitely with no error, no counter, and no alert.

4. **Partial-batch abort with no resume marker.** Only `fetch` is inside the `try`. `[VERIFIED]` `lib/sync-queue.ts:40` — `} catch {` closes a block whose only guarded call is the fetch; `incrementRetry`, `removeEntry` and `markFailed` all sit outside any handler. An IndexedDB `QuotaExceededError` or an aborted transaction on entry *k* throws out of `drainQueue` entirely, leaving 1..k-1 processed and k..N untouched, and `drainQueue` returns a `Promise` that no code in this repo attaches a `.catch` to — so it surfaces as an unhandled rejection, not as an error state the UI can render.

5. **No jitter.** The backoff array is a constant. Every handset that lost the same site uplink retries at the same five offsets. `[INFERENCE]` — a fleet-wide reconnect after a regional outage arrives as five synchronised spikes, which is how a recovering backend gets pushed back over before it has drained its own queue.

**Prescription** (grounded in the spec gate "Offline capture must survive poor connectivity and retry", which a 48-second give-up does not satisfy):

- Give the fetch an explicit timeout — `AbortSignal.timeout(...)` as `lib/notify.ts` already does — and state the value as a decision, not a default.
- Add `"failed"` to `getSyncStatus`: a non-zero failed count must return a distinct, alarming status that the capture UI blocks departure on. `SYNCED` must mean "the server has it", not "the queue is empty".
- Either extend retry to a duration matched to a real field shift (hours, with jitter) or make `failed` an explicitly operator-recoverable state with a re-queue path and a visible count. As written it is neither.
- Wrap the per-entry body so one storage error cannot abandon the remainder of the batch, and record the last-processed id so a resumed drain does not restart from the top.
- Reconcile the `Entry` status union with the strings `getSyncStatus` counts, so an unreachable branch becomes a compile error rather than a permanently-false alert condition.

**What would prove me wrong:** a server-side ingest counter compared against device capture counts over a week. `[UNCONFIRMED]` — I cannot run it from here; the query is a count of `public.reports` rows per tenant per day against the device-side capture log, and any positive gap is this bug.

## The watchdog cannot report its own failure

The detection path fails open at every step, and its failure is indistinguishable from health. This is the "alerting on rates rather than absence" trap: the thing that would tell you the system is dead is itself the thing most likely to be quietly dead.

`runWatchdog` only attempts an alert if `ALERT_EMAIL` is set, and returns normally when it is not:

`[VERIFIED]` `lib/notify.ts:25-30` — `const to = process.env.ALERT_EMAIL?.trim();` / `if (to) {` / `await sendEmail({ to, subject: ... });` / `alerted = true;` / `}` / `return { healthy: problems.length === 0, alerted };`

If `ALERT_EMAIL` is unset or is whitespace, `runWatchdog` returns `{healthy: false, alerted: false}` — a truthful object that nobody reads, because the caller wanted the side effect. There is no throw, no `console.error`, no metric. A misconfigured environment produces a system that has silently switched its own alarms off, and the only evidence is a boolean in a returned object.

`sendEmail` then swallows all three of its failure modes into `console.error` and resolves as `void`:

`[VERIFIED]` `lib/notify.ts:6-8` — `if (!key) {` / `console.error("[notify] RESEND_API_KEY unset, dropping mail", payload.subject);` / `return;`
`[VERIFIED]` `lib/notify.ts:17` — `if (!res.ok) console.error("[notify] non-2xx", res.status);`
`[VERIFIED]` `lib/notify.ts:18-19` — `} catch (e) {` / `console.error("[notify] send failed", e);`

Its own docblock states the intent — `[VERIFIED]` `lib/notify.ts:2` — `* Fire-and-forget: reports errors loudly but never throws, so callers do not fail.` For a transactional side-effect that is defensible. For the alerting channel it is the whole problem: `sendEmail` returning `Promise<void>` means `alerted = true` is set on line 28 whether or not a single byte left the process. The watchdog's own success signal is a lie by construction.

The concrete run: the Resend key is rotated and the new value is not deployed. Every subsequent watchdog cycle logs one line to stdout and returns `alerted: true`. Every dashboard built on `alerted` shows the watchdog running normally. The next real incident — the sync queue above, a stalled job, anything in `problems` — is detected, formatted, and dropped. Nobody learns until a customer calls. The blast radius is not one email; it is the whole detection surface, for as long as the key stays wrong.

**Prescription** (grounded in the contract's `observability` question — how anyone learns this broke without a customer telling them):

- `sendEmail` must return delivery outcome, not `void`, and `runWatchdog` must set `alerted` from that outcome rather than from the fact that it made a call.
- Missing `ALERT_EMAIL` or missing `RESEND_API_KEY` should fail startup, not fail each cycle silently. A service whose alerting is unconfigured is not a healthy service.
- Add a heartbeat with an **absence** alarm — "watchdog has not completed a cycle in N minutes" — on a channel that does not depend on `sendEmail`. Every mechanism above shares the single email path, so a single credential failure takes out detection entirely; a second, independent path is the only thing that catches that.
- `console.error` is not an alert unless something is watching stdout and paging on it. If nothing is, these five lines are a comment.

**I disagree in advance with any read of this as duplicate coverage**: `eng-observability` may also answer `observability`, and should — my claim here is narrowly that the alerting channel has no self-detection, not a general observability review. Merge both rather than picking one.
