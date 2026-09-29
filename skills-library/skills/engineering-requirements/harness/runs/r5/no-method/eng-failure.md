by: eng-failure
contributed: [eng-failure]
categories:
  failure_modes: {state: PRESCRIBED, ref: "#offline-queue-fails-silent", by: eng-failure, blocking: true}
  observability: {state: PRESCRIBED, ref: "#watchdog-never-runs-and-reports-success-anyway", by: eng-failure, blocking: true}
cross_domain:
  - "003_rls_fix.sql is not in APPLIED_LEDGER.txt, so the live DB still carries the 002 anon-read policy — eng-release owns the ledger drift, eng-authz the predicate"
  - "vitest.config.ts include globs are lib/**/__tests__/** but the only test sits at __tests__/engine.test.ts, so the suite passes having run nothing — eng-test owns test_oracle"
  - "a POST that succeeds server-side but whose response is lost is re-sent on the next drain and no idempotency key is carried, duplicating a reading — eng-concurrency"
  - "nothing defines which HTTP statuses the capture endpoint considers retryable, so the client invents the taxonomy — eng-contract"
  - "AuditLog cascades on Inspection delete in lib/schema.prisma, so the audit trail dies with the row it audits — eng-data"
  - "drainQueue has no guard against a second concurrent invocation (two tabs, a visibilitychange handler) — eng-concurrency"

## Offline queue fails silent

The spec's second gate is `> Offline capture must survive poor connectivity and retry.` The queue as written survives neither, and every way it fails is invisible to the technician standing in the building.

**1. The sync fetch has no timeout, and the drain is serial.** `[VERIFIED]` `lib/sync-queue.ts:33` — `const response = await fetch(entry.endpoint, {` — no `signal`, no `AbortSignal`. Browser `fetch` has no default timeout. Concrete scenario: a technician's device associates with a site's guest AP that is behind a captive portal; TCP connects, the request is accepted, no response is ever written. The `await` at line 33 never settles. Because the loop at `lib/sync-queue.ts:27` (`for (const entry of entries) {`) is serial, entries `k+1..N` are never attempted, entry `k`'s `retryCount` is never incremented, nothing throws, and `getSyncStatus` returns `PENDING_SYNC` for the rest of the shift with no error surface anywhere.

This is a silent decision, not a missing capability: the same repo already knows the idiom. `[VERIFIED]` `lib/notify.ts:15` — `signal: AbortSignal.timeout(10_000),`. **Prescribed:** a per-attempt `AbortSignal.timeout` (15s is the right order for a mobile uplink), an abort treated as a failed attempt so `incrementRetry` runs, and a wall-clock budget on the whole drain so one entry cannot consume the window.

**2. Terminally failed entries are unreachable *and* uncounted, so loss reports as success.** `[VERIFIED]` `lib/sync-queue.ts:29` — `await markFailed(db, entry.id);` — and `lib/sync-queue.ts:25` — `const entries: Entry[] = await getAll(index, "pending");`. Once an entry is `failed` no drain ever selects it again. Now the status function: `[VERIFIED]` `lib/sync-queue.ts:47-50` —

```
  const pendingCount = await count(db, "pending");
  const conflictCount = await count(db, "conflict");
  if (conflictCount > 0) return "SYNC_CONFLICT";
  if (pendingCount > 0) return "PENDING_SYNC";
```

`"failed"` is counted by nothing. Worse, `"conflict"` is not a value any code can write — `[VERIFIED]` `lib/sync-queue.ts:6` — `  status: "pending" | "failed";` — so `conflictCount` is structurally always `0` and `SYNC_CONFLICT` is dead code. Concrete scenario: 12 readings queued, one carries a payload the endpoint rejects with 422. It burns five attempts across ~48s of backoff, flips to `failed`, and `pendingCount` reaches 0. The UI then says **`SYNCED`**. The technician leaves site, the browser evicts IndexedDB a fortnight later, and a reading that was never accepted is gone with the interface having confirmed upload. This is a fail-open into wrongness: the cheapest possible signal (a count of a status the code already writes) was omitted.

**Prescribed:** `getSyncStatus` counts `failed` and returns a distinct terminal state; `SYNCED` becomes an assertion that `pending + failed + conflict === 0`, not merely `pending === 0`. Either implement `conflict` or delete the branch — a status value no writer can produce is a dashboard lie waiting to be believed.

**3. Permanent and transient failures are indistinguishable.** `[VERIFIED]` `lib/sync-queue.ts:38` — `      if (!response.ok) await incrementRetry(db, entry);`. A 422 gets the same five attempts as a 503, and a 503 that lasts eleven minutes gets only five. **Prescribed:** 4xx other than 408/429 fails immediately with the response status persisted on the entry so the failure is diagnosable; 5xx, 429 and network/abort errors retry.

**4. Retries are unjittered and shared across the fleet.** `[VERIFIED]` `lib/sync-queue.ts:2` — `const RETRY_BACKOFF_MS = [1000, 2000, 5000, 10000, 30000]; // exponential backoff`. Concrete scenario: 30 vans reach depot wifi within the same minute at shift end and drain simultaneously; the endpoint sheds load at 503; all 30 clients retry at exactly +1s, +2s, +5s, +10s, +30s in lockstep, so every recovery attempt by the server meets the full fleet at once and the brownout is held open until all clients exhaust `MAX_RETRY_COUNT` — at which point their data is silently discarded per finding 2. **Prescribed:** full jitter (`random(0, backoff)`). Note also that the array is not exponential despite the comment; whether the intended schedule was `1,2,4,8,16` is a decision nobody made on purpose.

`[INFERENCE]` on the operational shape of 1 and 4 — the mechanisms are read from the file, the fleet-timing scenario is judgement. `[UNCONFIRMED]`: whether a service worker or `visibilitychange` handler calls `drainQueue` on a schedule cannot be established from this tree — `grep -rn "drainQueue" .` over the fixture returns only the definition at `lib/sync-queue.ts:23`.

## Watchdog never runs and reports success anyway

`[VERIFIED]` by exhaustive grep of the fixture (12 files): `grep -rn "runWatchdog" .` returns exactly one hit, `lib/notify.ts:23` — `export async function runWatchdog(problems: string[]) {`. **Nothing invokes it.** No cron, no route, no scheduler. This is the exact shape of the failure that alerting exists to catch and cannot: a monitor that produces zero errors because it produces nothing at all, while a dashboard of error *rate* stays flat and green.

Three separate defects compound it, and all three survive wiring the caller up:

**The alert path reports success it did not achieve.** `[VERIFIED]` `lib/notify.ts:26-29` —

```
  if (to) {
    await sendEmail({ to, subject: `${problems.length} job(s) unhealthy` });
    alerted = true;
  }
```

`alerted` is set from the presence of an env var, not from the outcome. `sendEmail` cannot report an outcome — its contract is to swallow everything: `[VERIFIED]` `lib/notify.ts:8` — `    console.error("[notify] RESEND_API_KEY unset, dropping mail", payload.subject);` then `return;`, plus the non-2xx branch at `:17` and the `catch` at `:19`, all of which resolve `void`. Concrete scenario: Resend is down for 40 minutes, or `RESEND_API_KEY` was never set in the production environment. Every watchdog cycle returns `{healthy: false, alerted: true}`. Anything consuming that field — a status page, a run record, a retry decision — concludes an operator was told. Nobody was.

**A healthy run still emails.** The `if (to)` guard does not consult `problems.length`, so a clean cycle sends the subject `0 job(s) unhealthy`. Every cycle mails. The first genuine alert arrives in a folder that has been rule-filtered into oblivion.

**The one endpoint a monitor will poll asserts health it never checked.** `[VERIFIED]` `app/api/health/route.ts:2-6` — `  return Response.json({ status: "ok", ...})`. It touches no database, no queue, no dependency. It returns 200 with `"ok"` while Postgres is unreachable and every report write is failing. The spec's `> Deploy is repeatable and observable.` is not met by a route that is incapable of returning anything but `ok`.

**Prescribed:**
- `sendEmail` returns `{sent: true} | {sent: false, reason}` and `runWatchdog` derives `alerted` from it. A function that cannot fail is a function whose caller cannot be correct.
- Missing `ALERT_EMAIL` or `RESEND_API_KEY` fails loudly at process start, not silently per-send — a misconfigured deploy should be detectable in the first minute, not at the first incident.
- Alert only when `problems.length > 0`, and add a heartbeat the watchdog writes on every completed run with an external alarm on *absence* of that heartbeat. Without it, the failure verified above (nothing calls it) is undetectable by construction — its symptom is silence, and silence is what success looks like today.
- `/api/health` performs a bounded, timed dependency probe (`SELECT 1` with a ~2s timeout) and returns 503 on failure, so the monitor's green means something.

Disagreement note for the chair: `eng-observability` very likely also answers `observability`. I am claiming it because the finding is that the *detection* path itself fails open — the damage-travels-unnoticed question is my seat's — and I would rather both answers be merged than have this one quietly dropped.
