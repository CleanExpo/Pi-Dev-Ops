by: eng-observability
contributed: [eng-observability]
categories:
  observability:  {state: PRESCRIBED, ref: "#nothing-detects-this-system-stopping", by: eng-observability, blocking: true}
  failure_modes:  {state: PRESCRIBED, ref: "#the-only-alert-channel-reports-success-without-sending", by: eng-observability, blocking: true}
  data_model:     {state: N/A, reason: "This seat inspected no writer, owner or cascade rule; the one cascade concern I have is handed to eng-data below rather than claimed here."}
  test_oracle:    {state: N/A, reason: "The vitest include globs miss the only test file, which is a suite-configuration defect owned by eng-test; I hand it over rather than answer for it."}
cross_domain:
  - "vitest.config.ts:3-6 includes only `lib/**/__tests__/**` and `app/**/__tests__/**`, but the sole test file is `__tests__/engine.test.ts` at the repo root — zero files collected, and `passWithNoTests` is unset so the behaviour depends on the vitest default. eng-test owns whether the classification gate the spec requires actually runs."
  - "supabase/APPLIED_LEDGER.txt lists `001` and `002` only, while supabase/migrations/ contains 003_rls_fix.sql — the tenant-scoping fix is merged but not recorded as applied. eng-release owns the ledger/directory disagreement; I own only the fact that nothing observes it (below)."
  - "002_policies.sql grants SELECT/INSERT/UPDATE/DELETE to `anon` and 003 revokes only on `public.reports` — eng-authz owns whether the revoke is complete and whether the `user_tenant_access` predicate is right."
  - "lib/schema.prisma:20 puts `onDelete: Cascade` on AuditLog→Inspection, so deleting an inspection destroys its own audit trail. eng-data owns the cascade rule; my interest is that this is the record you would reach for during an investigation."

Where my instinct disagreed with the method, the method won: I wanted a tracing and metrics pipeline, and METHOD.md §1 says prescribe the boring version first — a health check that actually queries, one heartbeat row, and error-level logs carrying an id.

## Nothing detects this system stopping

The spec's own done-condition is `> Deploy is repeatable and observable.` Nothing in this repository observes anything. Every detection surface present is one that cannot report a fault.

**The health endpoint cannot fail.** `app/api/health/route.ts:3` — `    status: "ok",` — is a literal. The handler opens no database connection, reads no queue depth, and consults no migration state; it returns 200 with `status: "ok"` while Postgres is unreachable, while `003_rls_fix.sql` sits unapplied, and while every report distribution is failing. [VERIFIED] Any uptime monitor pointed at this route measures whether Next.js is running, which is the one failure a customer would have told you about anyway.

**The absence-shaped paths have no deadman.** `drainQueue` (`lib/sync-queue.ts:23`) emits nothing on entry, nothing on completion, and nothing on the count it processed. If the caller that invokes it — a service worker registration, a scheduler — stops firing, the system produces zero errors out of zero runs and every error-rate panel stays flat. A device that has never enqueued anything and a device whose sync has been dead for a week are indistinguishable: `lib/sync-queue.ts:51` — `  return "SYNCED";` — is reached in both cases, because it is the fall-through of two zero counts. [VERIFIED] I have watched exactly this hide a nightly job that had not run for two months.

**The retry path swallows the error entirely.** `lib/sync-queue.ts:40` is `    } catch {` — no binding, so the exception is not merely unlogged, it is unreachable. The only consequence of a failed upload is `incrementRetry`, which writes a counter into IndexedDB on the technician's device. After five attempts, `lib/sync-queue.ts:29` — `      await markFailed(db, entry.id);` — moves a captured field reading to a terminal `failed` state and emits nothing, to nowhere. [VERIFIED] That is silent loss of the primary artefact the product exists to capture, on the exact connectivity the spec says must be survived: `> Offline capture must survive poor connectivity and retry.`

**One indicator is wired to a state that is never written.** `lib/sync-queue.ts:48` — `  const conflictCount = await count(db, "conflict");` — but the type at `lib/sync-queue.ts:6` is `  status: "pending" | "failed";`. [VERIFIED] Nothing in this file can ever set `conflict`, so `SYNC_CONFLICT` is dead and the branch guarding it is a green light soldered on. An indicator that cannot turn red is worse than no indicator: it is a specific reassurance that a specific failure is not happening.

**No log line in the repository carries an actionable identifier.** `lib/notify.ts:17` — `    if (!res.ok) console.error("[notify] non-2xx", res.status);` — records a status code with no recipient, no problem list, no correlation id. [VERIFIED] You can watch that count rise and you cannot find one instance to reproduce.

Prescribed, and deliberately the boring version:

1. `/api/health` must be able to return 503. Minimum: one `SELECT 1` round-trip, and a count of applied migrations compared against the number of files in `supabase/migrations/` — non-equal is 503 with the missing ids in the body. That single check turns the unapplied `003` from a thing someone notices during a breach into a red deploy. It also discharges the spec's `> Migrations are applied and recorded.`
2. Two deadman alerts, phrased as absence and not as error rate: "no `drainQueue` completion reported in 26h" and "no report distributed in 26h". Both need a heartbeat write, because you cannot alert on the absence of something that never writes.
3. Every terminal transition in `drainQueue` — `markFailed`, and the `catch` — emits a structured error-level event carrying `entry.id`, `entry.endpoint`, `entry.retryCount` and the tenant. `markFailed` in particular is data loss and belongs at error, permanently exempt from any sampling or rate limiting that is later added, because it is rare by design and therefore the first thing uniform sampling deletes.
4. Delete the `conflict` branch, or add `"conflict"` to the union and write the code that sets it. Either is fine; a third state that only the reader believes in is not.

What would overturn this: if report distribution and queue drain are both invoked synchronously from a user request that already has upstream tracing, the deadman requirement drops to one — but nothing in this repository shows me that caller, so I am prescribing for the scheduled case.

## The only alert channel reports success without sending

`lib/notify.ts:2` documents the intent — `* Fire-and-forget: reports errors loudly but never throws, so callers do not fail.` — and the implementation is only half of that. It never throws, correctly. "Loudly" is `console.error` and nothing else. [VERIFIED]

The consequence is in the caller. `lib/notify.ts:27-28`:

```
    await sendEmail({ to, subject: `${problems.length} job(s) unhealthy` });
    alerted = true;
```

`alerted = true` is set on the basis of `sendEmail` having returned. `sendEmail` returns normally on all three of its failure paths: missing `RESEND_API_KEY` (`lib/notify.ts:8`, an early `return` after a console line), a non-2xx from Resend (`lib/notify.ts:17`), and a thrown fetch or a tripped 10s `AbortSignal.timeout` (`lib/notify.ts:18-20`). [VERIFIED] So `runWatchdog` returns `alerted: true` in every case where no mail was sent. This is success declared before the effect is durable — the flag asserts a delivery the transport never confirmed, and the discrepancy is invisible because nothing reconciles the two.

The second half is worse. `lib/notify.ts:25` — `  const to = process.env.ALERT_EMAIL?.trim();` — and the send is inside `if (to)`. [VERIFIED] With that variable unset, empty, or whitespace in one environment, `runWatchdog` returns `{ healthy: false, alerted: false }` and does nothing at all: no throw, no log, no retry. The watchdog runs, sees the problems, and has no mouth. Blast radius of a single missing env var is total loss of alerting for that environment, detectable only by reading a boolean that no code in this repository reads.

Prescribed:

1. `sendEmail` returns a discriminated result — `{ ok: true; id: string } | { ok: false; reason: "no_key" | "http_" + status | "network" }`. `runWatchdog` sets `alerted` only from `ok: true`, and emits an `alert_delivery_failed` event on anything else.
2. That failure event must not travel over Resend. An alert channel that reports its own outage through itself reports nothing. A second sink — stderr at error level is acceptable if stderr is actually shipped, which `/api/health` above should not be the only evidence of.
3. A missing `ALERT_EMAIL` or `RESEND_API_KEY` fails process startup, not the alert. This is METHOD.md §8 applied to configuration: fail where it cannot compile past you, not at 3am when the variable is finally needed.
4. The alerting path needs its own deadman — a synthetic problem fired on a schedule whose non-arrival is alerted independently. Without it, the first time anyone learns alerting is broken is the incident alerting existed to catch, and by then you are debugging two outages.

Per METHOD.md §6, points 1 and 3 are lint- and startup-enforceable rather than review-enforceable, and should be written as rules: no `await`-then-assume-success on a function whose return type is `Promise<void>`, and a single validated env schema at boot. The instance is the finding here only because the check is absent.
