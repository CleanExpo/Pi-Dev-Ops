by: eng-observability
contributed: [eng-observability]
categories:
  observability:  {state: PRESCRIBED, ref: "#nothing-in-this-system-emits-a-signal-about-its-own-state", by: eng-observability, blocking: true}
  failure_modes:  {state: PRESCRIBED, ref: "#the-alert-channel-cannot-report-its-own-failure", by: eng-observability, blocking: true}
  invariants:     {state: PRESCRIBED, ref: "#synced-is-reported-over-permanently-lost-captures", by: eng-observability, blocking: true}
cross_domain:
  - "vitest.config.ts include globs are `lib/**/__tests__/**/*.test.ts` and `app/**/__tests__/**/*.test.ts`, but the only test file is at `__tests__/engine.test.ts` (repo root) — the suite matches zero files and vitest exits 0, so 'tests gate the classification engine' is green on nothing. eng-test owns it."
  - "`supabase/APPLIED_LEDGER.txt` lists only `001` and `002`, yet `003_rls_fix.sql` exists — the tenant-scoping fix is merged and unapplied. eng-release owns the ledger/directory drift."
  - "migration 002 grants `SELECT, INSERT, UPDATE, DELETE ON public.reports TO anon` under a `USING (true)` policy, and only unapplied 003 revokes it — eng-authz owns whether prod is currently open."
  - "`RESEND_API_KEY` and `ALERT_EMAIL` are read directly from `process.env` with no startup validation — eng-secrets owns custody, I own the silence when they are absent."

## Nothing in this system emits a signal about its own state

The spec's done-condition is "Deploy is repeatable and observable." Nothing in the repo observes anything.

`app/api/health/route.ts:1-7` is a constant. It cannot fail:

> `return Response.json({ status: "ok", version: process.env.NEXT_PUBLIC_APP_VERSION || "1.0.0", timestamp: new Date().toISOString() });`

[VERIFIED] It does not touch the database, does not read the migration ledger, does not report queue depth, and reports a `version` taken from an env var that a stale deploy would carry forward unchanged. A monitor polling this endpoint returns green against a server whose database is unreachable, whose RLS policy is the permissive one from 002, and whose code is a week old.

`runWatchdog` (`lib/notify.ts:23`) is the only thing in the repo shaped like a detector, and **it has no caller**. [VERIFIED] `grep -rn 'drainQueue|runWatchdog' .` over the whole fixture returns only the definitions at `lib/sync-queue.ts:23` and `lib/notify.ts:23` — no scheduler, no cron, no route, no CI workflow, and no `.github/` directory exists. It also takes `problems: string[]` from a caller that does not exist, so nothing computes what the problems are either.

This is the exact shape of the failure my seat exists for: **if the sync drain or the watchdog stops executing entirely, no alert fires, because every existing signal is derived from an error that only occurs when the code runs.** Zero errors out of zero runs looks identical to healthy.

**Prescribed:**

1. **A deadman, not an error-rate alarm.** Persist `last_successful_drain_at` and `last_watchdog_run_at` server-side, and alert on *absence*: "no successful queue drain recorded in 26h", "no watchdog completion in 2h". The threshold must exceed one full period plus one retry window so a single miss does not page, and must be shorter than the interval at which an insurer would notice a missing report. [INFERENCE] Nightly jobs that stop being invoked are the failure I have watched go undetected for two months, because every dashboard was built on error rate.
2. **Make `/api/health` capable of returning non-200.** Minimum: one round-trip query against `public.reports`, and the count of migration files on disk compared to lines in `APPLIED_LEDGER.txt` — a mismatch is a 503 with the missing id in the body. Today that drift (003 unapplied) is invisible to every automated check in the repo. A health endpoint that has never returned a failure has never been tested as a health endpoint.
3. **`console.error` is not a log backend, and it carries no identifiers.** `lib/notify.ts:17` is:

   > `if (!res.ok) console.error("[notify] non-2xx", res.status);`

   [VERIFIED] No recipient, no report id, no tenant id, no correlation id. On a dashboard this becomes a count nobody can turn into a single reproducible instance. Every error-level emit on the network boundary must carry `{tenant_id, report_id, attempt}` and go to a structured sink, not stdout.

**What would overturn this:** a deployed monitor (Vercel cron, Supabase scheduled function, external uptime check) that already asserts absence. I found no configuration file of any kind in this tree — [UNCONFIRMED] for infrastructure defined outside the repo; `vercel project ls && vercel crons ls` and the Supabase dashboard's scheduled-functions list would settle it.

## The alert channel cannot report its own failure

`lib/notify.ts:23-31` returns a boolean the caller will treat as fact:

> `await sendEmail({ to, subject: \`${problems.length} job(s) unhealthy\` });`
> `alerted = true;`

[VERIFIED] `sendEmail` is declared `Promise<void>` and its own doc comment at `lib/notify.ts:1-3` states the intent:

> `* Fire-and-forget: reports errors loudly but never throws, so callers do not fail.`

[VERIFIED] It returns early when the key is missing (`lib/notify.ts:7-9`), swallows non-2xx (line 17), and swallows every network error and the 10s `AbortSignal.timeout` (lines 18-20). **There is no return path that distinguishes delivered from dropped.** So `alerted: true` is set unconditionally whenever `ALERT_EMAIL` is set, and is true when Resend returned 401 on a rotated key, when the request timed out, and when `RESEND_API_KEY` is unset in production.

Blast radius: this is the last-resort channel. When it fails silently, the system loses not one signal but *all* of them, and the only artifact recording the loss is a `console.error` line on a serverless instance that is about to be recycled. The second branch is worse — if `ALERT_EMAIL` is unset or whitespace, `to` is falsy at `lib/notify.ts:26`, the entire `if` body is skipped, `runWatchdog` returns `{healthy: false, alerted: false}`, and nothing anywhere reacts to `alerted: false`. [VERIFIED] no caller exists to react to it.

**Prescribed:**

- `sendEmail` returns `{delivered: boolean, providerMessageId?: string, reason?: string}` and `runWatchdog` propagates it. `alerted` is set from the provider's response, never from the fact that a call was attempted. [INFERENCE] "Success logged before the effect is durable" — the enqueue-vs-ack distinction — is the mechanism; here the code does not even reach enqueue.
- Missing `RESEND_API_KEY` or `ALERT_EMAIL` is a **boot failure**, not a runtime `console.error`. A notification system whose credentials are absent should refuse to start, because the state it degrades into is indistinguishable from healthy.
- A second, independent channel for watchdog output (the one thing that must not depend on the system it watches). If both channels are the same Resend account, a billing suspension takes out detection entirely.
- Synthetic delivery probe: a scheduled send to a sink address, with its own deadman. An alert path never exercised in the healthy case is an alert path first tested during the incident.

## SYNCED is reported over permanently lost captures

`lib/sync-queue.ts:46-52` is the technician's only feedback that their field readings reached the server:

> `const pendingCount = await count(db, "pending");`
> `const conflictCount = await count(db, "conflict");`
> `if (conflictCount > 0) return "SYNC_CONFLICT";`
> `if (pendingCount > 0) return "PENDING_SYNC";`
> `return "SYNCED";`

[VERIFIED] It counts `pending` and `conflict`. It never counts `failed`. But `failed` is the terminal state the drain loop writes at `lib/sync-queue.ts:28-30`:

> `if (entry.retryCount >= MAX_RETRY_COUNT) { await markFailed(db, entry.id); continue; }`

[VERIFIED] And the catch that produces those retries records nothing at all — `lib/sync-queue.ts:40` is a bare `} catch {`, with no binding, no log, and no counter. The error that killed five attempts is discarded five times.

**Concrete scenario, inputs and timing:** a technician captures readings in a basement on cellular. Six attempts over ~48s of backoff (`[1000, 2000, 5000, 10000, 30000]`, `lib/sync-queue.ts:2`) all fail. `retryCount` reaches 5, `markFailed` runs, the entry leaves `pending`. The next `getSyncStatus` call finds `pendingCount === 0`, `conflictCount === 0`, and returns **`"SYNCED"`**. The technician closes the app believing the job is uploaded. The readings exist only in that browser's IndexedDB, no server-side record was created, and no log line names the entry id or the reason.

Compounding it: `conflictCount` can never be non-zero. `Entry.status` is declared at `lib/sync-queue.ts:7` as:

> `status: "pending" | "failed";`

[VERIFIED] Nothing in the type or the code can produce `"conflict"`. The `SYNC_CONFLICT` branch is unreachable — a status the type system already proves impossible, sitting above the status that actually occurs and is not checked.

**The invariant, as a testable assertion:**

> `getSyncStatus(db)` returns `"SYNCED"` **only if** the queue object store contains zero entries in any status. Not zero *pending* entries — zero entries.

Make it a test that seeds one `failed` entry and asserts the return is not `"SYNCED"`, and add `"failed"` to the `Entry` status union check so a new status cannot be introduced without the exhaustiveness check failing to compile. [INFERENCE] Per method §8, this belongs at the type boundary: a discriminated union with an exhaustive `switch` makes the next added status a compile error rather than a silent fall-through to `"SYNCED"`.

**Also prescribed here:** bind the error at `lib/sync-queue.ts:40` and emit one warn-level line per retry and one error-level line per `markFailed`, each carrying `entry.id`, `entry.endpoint`, `retryCount` and the error message; and surface `failedCount` to the server on next connect, so permanent capture loss is countable centrally rather than only on the device that lost it. Log sampling, if ever added, must exempt these — a rare terminal failure in a hot drain loop is exactly what uniform sampling deletes.

**Note on lane:** the retry/ordering semantics of this loop are eng-concurrency's; I claim only that its outcome is unobservable and that the status string it feeds asserts something false.
