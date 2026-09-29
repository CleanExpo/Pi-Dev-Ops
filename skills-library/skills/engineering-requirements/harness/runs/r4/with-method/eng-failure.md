by: eng-failure
contributed: [eng-failure]
categories:
  failure_modes: {state: PRESCRIBED, ref: "#failure-modes", by: eng-failure, blocking: true}
cross_domain:
  - "vitest `include` globs match no file — the only test sits at `__tests__/engine.test.ts` while the config expects `lib/**/__tests__/**`, so the suite is green on zero tests — eng-test owns it"
  - "`003_rls_fix.sql` is on disk but absent from `APPLIED_LEDGER.txt`, so the permissive `USING (true)` policy and the anon DML grants from 002 are what is actually live — eng-release owns the ledger drift, eng-authz owns the policy"
  - "`003` selects from `public.user_tenant_access`, which no migration in this repo creates; its `DROP POLICY` runs before that failure — eng-data/eng-release own what the table looks like in the gap"
  - "`drainQueue` reads a snapshot of pending entries then awaits per entry, so two overlapping invocations (online event plus interval) both POST the same entry — eng-concurrency owns it"
  - "`runWatchdog` sets `alerted = true` from a `sendEmail` that returns normally when the API key is unset or the send 4xx'd — the alert path reports success it did not have — eng-observability owns it"
  - "the spec's gate 'a report may not be distributed unless its verification checklist is complete' has no corresponding code or column anywhere in the repo — that is an `invariants` finding for the chair"
  - "`/api/health` returns `status: \"ok\"` unconditionally with no dependency probe, so it stays green through every failure below — eng-observability owns it"

## Failure modes

Three mechanisms in the offline sync path each end in the same place: readings the technician believes are captured are not on the server, and nothing in the system says so. The spec asserts the requirement — "Offline capture must survive poor connectivity and retry" — but nothing answers what happens once retry is exhausted, so this is `PRESCRIBED`, not `DECIDED`.

### 1. `failed` is a black hole, and the UI reports SYNCED on top of it

`lib/sync-queue.ts:28-30` retires an entry after five attempts: `if (entry.retryCount >= MAX_RETRY_COUNT) { await markFailed(db, entry.id); continue; }` [VERIFIED]. Nothing ever reads it again — the drain only selects one status, `lib/sync-queue.ts:25`: `const entries: Entry[] = await getAll(index, "pending");` [VERIFIED]. And nothing counts it: `lib/sync-queue.ts:47-51` counts `"pending"` and `"conflict"` only, so a queue holding nothing but failed entries falls through to `return "SYNCED";` [VERIFIED].

The `conflict` branch is structurally dead — `"conflict"` is not a member of the status union at `lib/sync-queue.ts:7`: `status: "pending" | "failed";` [VERIFIED] — so `SYNC_CONFLICT` can never be returned. An alert path that cannot fire is worse than no alert path, because it reads as coverage.

Concrete: technician works a basement, five attempts burn 48 seconds of backoff (1+2+5+10+30 s), all fail. The entry flips to `failed`, the app shows SYNCED, the technician leaves site, the server generates a report from the readings it does have, and that report is distributed to an insurer. No error counter increments, because nothing threw. Time to detection is however long until a human compares the report against the job — which for the insurer-facing artifact this spec describes may be never. This is the fail-open-into-wrongness pattern: the failure state was given a name and then given no reader.

**Prescribe:** `getSyncStatus` counts `failed` and returns a distinct terminal status; report generation refuses to run for an inspection with any `pending` or `failed` entry, rather than treating absence of data as absence of readings. Either add `"conflict"` to the union and populate it, or delete the branch.

*Method note (#1, boring version first):* my instinct was a dead-letter store with a replay UI. The boring version — count `failed` in the status the UI already renders — closes the data-loss path, and nothing here has yet measured that the replay UI is needed. Simplicity wins; the DLQ is a `DEFERRED` question for the first support ticket about a lost capture.

### 2. The drain fetch has no timeout, and the loop is sequential

`lib/sync-queue.ts:33-37` constructs the request with `method`, `headers` and `body` and no `signal` [VERIFIED]. The same repo already knows to do this: `lib/notify.ts:15`: `signal: AbortSignal.timeout(10_000),` [VERIFIED]. Browsers apply no default `fetch` timeout, so the `await` at line 33 has no upper bound [INFERENCE — this is the standard `fetch` contract; the mechanism I have watched fail is a captive portal or carrier NAT that completes the TCP handshake and then never sends bytes, which is exactly the "poor connectivity" the spec names].

Because the drain is a serial `for` loop, that one socket blocks entry 2..N indefinitely. A queue of thirty captures stalls behind the first, and `getSyncStatus` correctly reports `PENDING_SYNC` forever with no indication that progress has stopped rather than slowed.

**Prescribe:** per-attempt `AbortSignal.timeout()` on the drain fetch, matching notify.ts's 10s until something measures otherwise, plus a wall-clock cap on the whole drain so a caller can tell "still working" from "wedged".

### 3. Retry re-sends the request, not the missing effect — there is no idempotency key

Both the non-2xx path and the throw path funnel into `incrementRetry` and a later re-POST (`lib/sync-queue.ts:38`: `if (!response.ok) await incrementRetry(db, entry);`, and line 40-42's bare `catch { await incrementRetry(db, entry); }`) [VERIFIED]. The headers carry no dedupe token — `lib/sync-queue.ts:35`: `headers: { "content-type": "application/json" },` [VERIFIED], and `grep -rn "Idempotency\|idempot"` over the fixture returns nothing [VERIFIED].

Two real interleavings:

- The POST reaches the server and commits, then the response is lost — mobile handoff between cells, the tab is closed, or a proxy returns 502 after the origin already wrote. The entry is still pending, so the next drain sends it again. Duplicate readings inflate the report that goes to the insurer.
- A malformed payload returns 400. `!response.ok` does not distinguish it from a 503, so the client spends five attempts and 48 seconds on a request that can never succeed, then drops it into the black hole in §1. The technician is told nothing, and the server sees five identical rejections it also does not alert on.

**Prescribe:** send `Idempotency-Key: entry.id` and dedupe on it server-side; split retryable (network error, 5xx, 429) from non-retryable (4xx), failing the latter immediately and visibly. Add jitter to the fixed backoff table at `lib/sync-queue.ts:2` before a second client exists — a fleet of technicians that lost connectivity in the same building all re-attempt at the same five offsets.

**What would overturn §3:** an ingest handler that already dedupes on an id inside the payload body. There is no server-side ingest route in this repo (`app/api/` contains only `health/route.ts`), so today the client is the only place that key can originate. If the handler lands with dedupe built in, cut this finding.
