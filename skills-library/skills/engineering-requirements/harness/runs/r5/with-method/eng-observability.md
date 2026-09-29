by: eng-observability
contributed: [eng-observability]
categories:
  observability:  {state: PRESCRIBED, ref: "#nothing-here-can-report-that-something-stopped", by: eng-observability, blocking: true}
  failure_modes:  {state: PRESCRIBED, ref: "#a-permanently-failed-capture-reports-synced", by: eng-observability, blocking: true}
  invariants:     {state: PRESCRIBED, ref: "#alerted-true-is-asserted-without-proof-of-delivery", by: eng-observability}
cross_domain:
  - "003_rls_fix.sql is in migrations/ but not in APPLIED_LEDGER.txt — eng-release owns the ledger/pipeline, eng-authz owns the permissive 002 policy still live because of it; I only claim that nothing detects the drift"
  - "vitest.config.ts include globs are lib/**/__tests__/ and app/**/__tests__/, and the only test file is __tests__/engine.test.ts at the repo root — zero tests are collected; eng-test owns whether that is a passing suite"
  - "Entry.status is typed \"pending\" | \"failed\" but getSyncStatus counts \"conflict\" — a dead branch and a possible unfinished status migration; eng-data owns the type"

## Nothing here can report that something stopped

The spec's done-when says the deploy must be "observable", but nothing in the repo observes anything. There is no logger, no metrics client, no tracer, no error reporter, no CI config and no scheduler: `grep -rniE 'logger|sentry|otel|metric|datadog|console\.' --include='*.ts' .` returns three `console.error` lines in `lib/notify.ts` and nothing else. `[VERIFIED]` — the only three hits are `lib/notify.ts:7` `console.error("[notify] RESEND_API_KEY unset, dropping mail", payload.subject);`, `lib/notify.ts:17` and `lib/notify.ts:19`.

The single observation surface is a constant:

`[VERIFIED]` `app/api/health/route.ts:3` — `status: "ok",`

That literal is returned unconditionally. It never opens a database connection, never reads the migration ledger, never counts queue depth. An uptime monitor pointed at `/api/health` stays green while Postgres is unreachable, while `003_rls_fix.sql` has still not been applied, and while every technician's queue is stuck. It answers "is the Next.js process running", which is the one failure that already pages you.

There is also no invocation record for the two things that matter. `drainQueue` (`lib/sync-queue.ts:23`) and `runWatchdog` (`lib/notify.ts:23`) have no caller, cron, service-worker registration or scheduler anywhere in the tree — `grep -rn -E 'runWatchdog|drainQueue' --include='*.ts' .` returns only the two definitions. `[VERIFIED]`. This is the exact shape of the failure I have been on the wrong side of: the job stops being *invoked*, so it emits zero errors out of zero runs, and every error-rate alert stays flat and green for weeks. `runWatchdog` is also passed `problems: string[]` by its caller, so whatever computes "unhealthy" lives outside this change entirely and is unreviewable from here. `[INFERENCE]`

Prescribed, all three, before this is code:

1. `/api/health` must be a *dependency* check, not a literal: a `SELECT 1` against Postgres, the count of migration files in `supabase/migrations/` versus lines in `APPLIED_LEDGER.txt`, and it must return HTTP 503 when either fails. A health endpoint that cannot return non-200 is not a health endpoint. This is grounded in method §10 — a check that has never been observed failing has not been verified to work; the deploy gate should include one deliberate red run.
2. A deadman, not an error-rate alert: "no successful `drainQueue` completion recorded in 26h" and "no report distributed in 26h" must page. Absence is the failure mode here, and error-rate alerting is structurally blind to it.
3. Every log line on the sync and distribution paths carries `tenant_id`, `report_id` and `entry.id`. Today a failure produces no line at all; a line saying "sync failed" with no identifier is only marginally better, because you can watch the count rise on a dashboard and never reproduce a single instance.

The observation that would overturn this: a monitoring stack configured outside this repo (a Vercel cron, a Supabase scheduled function, a Grafana deadman) that already invokes and watches these paths. `[UNCONFIRMED]` — I cannot see it from here. `ls -a` shows no `.github/`, no `vercel.json`, no `*.yml`; run `git log --diff-filter=D -- .github vercel.json` to check one was not removed.

## A permanently failed capture reports SYNCED

Concrete scenario. A technician captures readings in a basement on 4G. `fetch` throws — DNS failure, captive portal, dropped connection. Control reaches:

`[VERIFIED]` `lib/sync-queue.ts:40` — `    } catch {`

A bare `catch` with no binding. The error object is not just unlogged, it is not even captured — there is no variable to log. `incrementRetry` runs. This repeats until `entry.retryCount >= MAX_RETRY_COUNT` (`lib/sync-queue.ts:28`, `[VERIFIED]`: `    if (entry.retryCount >= MAX_RETRY_COUNT) {`), at which point `markFailed` moves the entry to status `"failed"` and `continue`s. Not one line is emitted at any point in that sequence — five silent retries and a permanent give-up, client-side and server-side both.

Then the status the technician is shown:

`[VERIFIED]` `lib/sync-queue.ts:46-52` —
> ```
>   const pendingCount = await count(db, "pending");
>   const conflictCount = await count(db, "conflict");
>   if (conflictCount > 0) return "SYNC_CONFLICT";
>   if (pendingCount > 0) return "PENDING_SYNC";
>   return "SYNCED";
> ```

`"failed"` is counted by neither branch. Once the last entry crosses `MAX_RETRY_COUNT`, `pendingCount` drops to zero and `getSyncStatus` returns `"SYNCED"`. The technician's UI says their work is safe at the exact moment it has been abandoned. The blast radius is the full contents of a job that a human believes is filed, discovered when an insurer asks for a report that does not exist. `[INFERENCE]` — I have watched this precise pairing (terminal state excluded from the status rollup) turn a retry ceiling into silent data loss.

Prescribed: `getSyncStatus` must have a `failedCount` branch returning a distinct terminal state ahead of the `SYNCED` return, and reaching `MAX_RETRY_COUNT` must emit an error-level event carrying `entry.id`, `entry.endpoint` and the last error, plus a counter the server can alert on. The `catch` must bind and log the error at warn on each attempt; log sampling, if it is ever added, must exempt error level, or a rare failure in this hot loop is sampled out of existence. Method §6 applies: this will recur, so the durable form is a lint rule banning bare `catch {}` and an exhaustive switch over `Entry["status"]` in the status rollup, not a one-time correction.

I expect `eng-failure` to also claim `failure_modes` for the data-loss blast radius. I am claiming only the detection half — that no signal exists — and defer the recovery design to that seat.

## alerted true is asserted without proof of delivery

`sendEmail` is documented as never throwing, and it honours that:

`[VERIFIED]` `lib/notify.ts:1-3` —
> ```
> /**
>  * Fire-and-forget: reports errors loudly but never throws, so callers do not fail.
>  */
> ```

Its return type is `Promise<void>`. A missing `RESEND_API_KEY` returns early (`lib/notify.ts:8`), a non-2xx from Resend only `console.error`s (`lib/notify.ts:17`), and a network failure or the 10s `AbortSignal.timeout` is caught and logged (`lib/notify.ts:19`). All four outcomes are indistinguishable to the caller. The caller then does this:

`[VERIFIED]` `lib/notify.ts:27-28` —
> ```
>     await sendEmail({ to, subject: `${problems.length} job(s) unhealthy` });
>     alerted = true;
> ```

`alerted: true` is set on the line after a call that cannot report failure. The invariant a reader will assume — *`alerted === true` implies a human was notified* — is false in every failure branch. Worse, the branch that matters most is the silent one: if `ALERT_EMAIL` is unset or whitespace, `if (to)` is false (`lib/notify.ts:25-26`, `[VERIFIED]`: `  const to = process.env.ALERT_EMAIL?.trim();`), `runWatchdog` returns `{healthy: false, alerted: false}` and emits **no log line at all**. One unset environment variable disables the entire alerting path, and the only record of that is a boolean nobody is reading. This is the same mechanism as declaring a write durable at enqueue rather than at commit: the log line asserts something the delivery layer never confirmed.

State the invariants as assertions someone could test:
- `runWatchdog(problems).alerted === true` ⇒ the provider returned 2xx for that message. Enforce it by having `sendEmail` return a discriminated result (`{ok: true, id} | {ok: false, reason}`) and setting `alerted` from `res.ok`. Method §8: make the contract enforceable at the type boundary rather than by a comment claiming the function is safe.
- `problems.length > 0 && alerted === false` must be impossible without an error-level event naming the reason. The unconfigured-alerting case specifically must fail loudly at boot: assert `ALERT_EMAIL` and `RESEND_API_KEY` are present at startup and refuse to start without them, rather than discovering at the first incident that the alert channel was never wired.
- The alerting path itself needs one synthetic delivery per deploy that is asserted on. Per method §10, an alert channel that has never been observed delivering is an untested code path that only runs during an outage.

`[UNCONFIRMED]` on the caller's intent: `runWatchdog` receives `problems` pre-computed and has no in-repo caller, so I cannot see whether the returned `alerted` is persisted, dashboarded or discarded. `grep -rn 'runWatchdog' --include='*.ts' --include='*.tsx' <the repo that calls this>` would settle it. If it is discarded, the finding is unchanged and slightly worse: the only record of whether anyone was told is thrown away.
