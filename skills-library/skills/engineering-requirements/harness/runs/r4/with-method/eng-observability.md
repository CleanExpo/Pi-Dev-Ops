by: eng-observability
contributed: [eng-observability]
categories:
  observability: {state: PRESCRIBED, ref: "#observability", by: eng-observability, blocking: true}
  failure_modes: {state: PRESCRIBED, ref: "#failure-modes", by: eng-observability, blocking: true}
  invariants:    {state: PRESCRIBED, ref: "#invariants",    by: eng-observability, blocking: true}
cross_domain:
  - "vitest include globs are lib/**/__tests__ and app/**/__tests__ but the only test file is __tests__/engine.test.ts at repo root — zero tests execute and the suite still reports green — eng-test owns test_oracle"
  - "003_rls_fix.sql exists but APPLIED_LEDGER.txt records only 001 and 002, so production is presumed still running the permissive 'Anon read access' USING (true) policy — eng-release owns the ledger, eng-authz owns the predicate"
  - "AuditLog.inspection carries onDelete: Cascade, so deleting an inspection destroys its own audit trail — eng-data owns the cascade rule"
  - "spec gate 'A report may not be distributed unless its verification checklist is complete' has no implementing code anywhere in the repo — eng-contract owns the gate's shape"
  - "drainQueue and runWatchdog have no caller in this repo (grep for both returns only their definitions) — eng-concurrency owns what invokes the drain and on what schedule"

## observability

The spec's own exit condition is `> Deploy is repeatable and observable.` Nothing in this repo can observe anything. The entire telemetry surface is three `console.error` calls in one file — no counter, no structured log, no request id, no tenant id, no heartbeat. [VERIFIED] `grep -rniE 'logger|metric|sentry|otel|telemetry|trace|counter|console\.'` over `*.ts` returns exactly `lib/notify.ts:7`, `:17`, `:19` and nothing else.

**The health endpoint cannot go red.** [VERIFIED] `app/api/health/route.ts:2-3` — `return Response.json({ status: "ok",`. There is no branch, no probe, no dependency check; the handler returns 200 `ok` for every input. A process that is up but cannot reach Postgres, has an unapplied migration, or has a dead sync consumer reports `ok`. Any uptime monitor pointed here is a check that has never been proven able to fail — a green board and an outage are the same observation.

**Nothing detects absence.** My question for this repo: if `drainQueue` stopped executing entirely, which alert fires and how long until it does? None, ever. [VERIFIED] `lib/sync-queue.ts:23` — `export async function drainQueue(db: IDBDatabase) {` — the function is client-side, writes only to IndexedDB on the technician's device, and emits nothing server-side on success or failure. A service worker that fails to register, or a field device left on airplane mode, produces zero rows, zero errors, and zero signal. The failure surfaces when an insurer asks where the report is. [INFERENCE] This is the exact shape of the nightly-job-stopped-two-months-ago failure: alerting on error rate over a path that is no longer invoked gives zero errors out of zero runs.

**The catch discards the identity of the failure.** [VERIFIED] `lib/sync-queue.ts:40` — `} catch {` — the error is not even bound, so nothing distinguishes "device offline" from "server returned 500" from "payload rejected as malformed". [VERIFIED] `lib/sync-queue.ts:38` — `if (!response.ok) await incrementRetry(db, entry);` — the status code is not recorded either, so an expired auth token returning 403 forever and a transient 503 burn the same five attempts and then reach [VERIFIED] `lib/sync-queue.ts:29` — `await markFailed(db, entry.id);` — which logs nothing and notifies nobody. A capture is permanently lost, on-device, with no record that it ever existed.

**Ledger drift is undetected.** `supabase/APPLIED_LEDGER.txt` contains `001` and `002`; `supabase/migrations/` contains `003_rls_fix.sql`. No check in the repo compares the two, so the pipeline cannot tell anyone that the tenant-isolation fix was never applied. eng-release very likely answers this same category from the release angle; both readings should stand — mine is that the drift is invisible, theirs is that it happened.

Prescribed, grounded in the fact that these three are the only paths the spec names as gates (offline capture, report distribution, tenant isolation):

1. `/api/health` probes its dependencies and returns 503 when any fails. Ship a test that forces a dependency failure and asserts a non-200 — an endpoint that has never returned non-200 in any environment is not a health check.
2. A server-side deadman per gate, evaluated on a schedule independent of the path it watches: "no capture accepted from tenant T in 26h", "no report distributed in 26h", "migration ledger != migrations directory". Alert on absence of success, never on presence of error.
3. Every `catch` on the sync boundary binds the error and emits one warn-level record carrying `entry.id`, `endpoint`, `retryCount`, and either the HTTP status or the exception name. `markFailed` emits at error level with the same identifiers. Terminal data loss is not a debug-level event.
4. Whatever log sampling gets added later exempts warn and error. [INFERENCE] Uniform sampling applied to a hot drain loop is how a rare permanent failure gets sampled out of existence.

## failure-modes

The alerting path degrades to a no-op and reports that it succeeded. That makes it worse than having no watchdog, because a `alerted: true` in a run record is a false negative someone will trust.

[VERIFIED] `lib/notify.ts:27-28`:
```
    await sendEmail({ to, subject: `${problems.length} job(s) unhealthy` });
    alerted = true;
```
`sendEmail` is documented as [VERIFIED] `lib/notify.ts:3` — `* Fire-and-forget: reports errors loudly but never throws, so callers do not fail.` — and it honours that. [VERIFIED] `lib/notify.ts:6-9` — `if (!key) { console.error("[notify] RESEND_API_KEY unset, dropping mail", payload.subject); return; }`. So with `RESEND_API_KEY` unset, or the Resend API returning 500, or the 10s `AbortSignal.timeout` firing, `sendEmail` returns normally and the caller sets `alerted = true`. The return value asserts delivery the transport never confirmed.

Second leg: [VERIFIED] `lib/notify.ts:25-29` — `const to = process.env.ALERT_EMAIL?.trim(); if (to) {` — an unset or empty `ALERT_EMAIL` skips the send with no log at all. A single missing env var in one environment silently converts every alert into nothing, and nothing distinguishes "healthy, so no alert needed" from "unhealthy, but the alerter is unconfigured".

Blast radius: [INFERENCE] `runWatchdog` is the only alerting mechanism in the repo. When it no-ops, every failure this system has — unsynced captures, undistributed reports, a cross-tenant read — becomes discoverable only by an insurer or a technician complaining. The watchdog is the detector for everything else and has no detector of its own.

Prescribed:
- `sendEmail` returns a discriminated result (`{ok: true} | {ok: false, reason}`) rather than `void`; `runWatchdog` sets `alerted` only on `ok: true` and returns the reason otherwise. Type the boundary so "we alerted" cannot be asserted without the transport agreeing.
- Missing `ALERT_EMAIL` or `RESEND_API_KEY` fails startup in any environment where the watchdog runs, rather than being handled at call time. A misconfiguration that only manifests during an incident is discovered during an incident.
- One synthetic alert per day through the real transport, with its own deadman ("no synthetic alert delivered in 26h"). An alert channel that has not delivered anything since the last real incident is untested.

## invariants

Assertion that must hold and currently does not: **a device must never report `SYNCED` while any entry is in a non-terminal-success state.**

[VERIFIED] `lib/sync-queue.ts:46-52`:
```
export async function getSyncStatus(db: IDBDatabase) {
  const pendingCount = await count(db, "pending");
  const conflictCount = await count(db, "conflict");
  if (conflictCount > 0) return "SYNC_CONFLICT";
  if (pendingCount > 0) return "PENDING_SYNC";
  return "SYNCED";
}
```
Two defects, both making the status signal lie in the direction of false comfort:

`failed` is never counted. [VERIFIED] `lib/sync-queue.ts:29` moves an exhausted entry out of `pending` via `markFailed`. Concrete sequence: technician captures a reading in a basement, five drain attempts fail over roughly 48 seconds of backoff, `markFailed` runs, `pendingCount` drops to 0, and `getSyncStatus` returns `"SYNCED"`. The one screen that tells a technician whether their day's work reached the server says it did, at the exact moment it permanently did not.

`"SYNC_CONFLICT"` is unreachable. [VERIFIED] `lib/sync-queue.ts:7` — `status: "pending" | "failed";` — `"conflict"` is not a member of the union and no code path writes it. [VERIFIED] `grep -rn 'conflict' --include='*.ts'` returns only `lib/sync-queue.ts:48` and `:49`, the read and the branch. `count(db, "conflict")` therefore returns 0 forever and the branch is dead. [INFERENCE] A detector whose positive case has never fired in any environment is indistinguishable from a detector that is broken; this one is provably the latter.

Prescribed:
- `getSyncStatus` returns `"SYNC_FAILED"` when `count(db, "failed") > 0`, and the branch precedes the `"SYNCED"` return. `"SYNCED"` becomes reachable only when all three counts are zero.
- Either write `"conflict"` somewhere and add it to the `Entry["status"]` union, or delete the branch. Make `count`'s status parameter typed as `Entry["status"]` so a status the type does not know about cannot compile — this class of dead branch should be caught by `tsc`, not by review.
- A test that seeds one `failed` entry and asserts `getSyncStatus() !== "SYNCED"`. Run it against the current code first and confirm it fails; a test written after the fix that has never been seen red proves nothing.
