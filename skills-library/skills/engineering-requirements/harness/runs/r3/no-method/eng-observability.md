by: eng-observability
contributed: [eng-observability]
categories:
  observability:  {state: PRESCRIBED, ref: "#nothing-observes-whether-the-deploy-is-running-the-code-you-shipped", by: eng-observability, blocking: true}
  invariants:     {state: PRESCRIBED, ref: "#synced-must-not-be-reportable-while-an-entry-has-been-abandoned", by: eng-observability, blocking: true}
  failure_modes:  {state: PRESCRIBED, ref: "#the-alert-path-cannot-report-its-own-failure", by: eng-observability, blocking: true}
cross_domain:
  - "003_rls_fix.sql is in the migrations directory but not in APPLIED_LEDGER.txt — eng-release owns whether it ran"
  - "002_policies.sql grants anon SELECT/INSERT/UPDATE/DELETE with a USING (true) policy — eng-authz owns the predicate"
  - "vitest.config.ts include globs are lib/** and app/**; the only test file is at repo-root __tests__/ — eng-test owns the empty-run"
  - "drainQueue's terminal markFailed discards the technician's captured payload with no dead-letter store — eng-data owns where it goes"

## Nothing observes whether the deploy is running the code you shipped

The spec's done-condition is `> Deploy is repeatable and observable.` (`spec.md:13`). The only observation surface in the repo is a route that cannot fail:

```
app/api/health/route.ts:2-6   return Response.json({
                                status: "ok",
                                version: process.env.NEXT_PUBLIC_APP_VERSION || "1.0.0",
```
`[VERIFIED]` — the whole file is seven lines; it opens no database handle, reads no migration state, and the literal `"ok"` is unconditional.

Concrete scenario, and it is the state the repo is in right now. `supabase/migrations/` contains `003_rls_fix.sql`, whose first line is `> -- Tenant-scoped replacement for the permissive policy in 002.` `[VERIFIED] supabase/migrations/003_rls_fix.sql:1`. `supabase/APPLIED_LEDGER.txt` contains exactly two lines, `001` and `002` `[VERIFIED] supabase/APPLIED_LEDGER.txt:1-2`. So the tenant-scoping migration is merged and unapplied, the database is still serving the `> CREATE POLICY "Anon read access" ON public.reports FOR SELECT USING (true);` from `supabase/migrations/002_policies.sql:3-4`, and `/api/health` returns `200 {"status":"ok"}` throughout. Every uptime monitor, every deploy smoke check, and every dashboard fed by that route reads green while the third spec gate — `> Tenants must not read each other's reports.` (`spec.md:11`) — is unenforced in production. The time-to-detect for this class of drift is "until a tenant reports seeing someone else's report," which is exactly the page-by-customer-email failure this seat exists to prevent.

`version` is no help either: it is served from `NEXT_PUBLIC_APP_VERSION` with a hardcoded `"1.0.0"` fallback `[VERIFIED] app/api/health/route.ts:4`, so an environment where the variable is unset — the default, since nothing in the repo sets it — reports the same version forever, across every deploy. A responder comparing "what version is prod on" against a release tag gets a constant.

Prescription, grounded in the fact that migration state is the one piece of deploy state this repo already records in a file:

1. `/api/health` must reach the database and report the highest applied migration id read from the live schema-migrations source, not from `APPLIED_LEDGER.txt`. A build artifact cannot observe a database.
2. Add a second, separate route or check that compares that live id against the highest file in `supabase/migrations/` baked into the image, and returns non-200 when they differ. Liveness ("Node is up") and correctness ("the schema is the one this build expects") must be two signals, because a restart fixes the first and never the second.
3. The version string must fail closed: build-time injection of the commit sha, and no literal fallback. If it is unset the check should be red, not `"1.0.0"`.
4. `[UNCONFIRMED]` — there is no CI or deploy configuration in the repo at all (`find . -type f` returns twelve files, none under `.github/`, no Dockerfile, no `package.json`). Whoever owns the pipeline should run `git log --diff-filter=A -- .github/` to confirm it was never there rather than removed, and the drift check above must be wired as a post-deploy gate, not a dashboard tile someone is expected to look at.

## SYNCED must not be reportable while an entry has been abandoned

State it as the assertion: **`getSyncStatus()` may return `"SYNCED"` only when no entry exists in any non-terminal-success state.** It is violated today, and violated silently.

The queue's terminal path drops the entry out of observation entirely:

```
lib/sync-queue.ts:28-31   if (entry.retryCount >= MAX_RETRY_COUNT) {
                            await markFailed(db, entry.id);
                            continue;
                          }
```
`[VERIFIED]`. No log line, no counter, no user-visible event — `markFailed` flips status and `continue` moves on.

The status reporter then cannot see it:

```
lib/sync-queue.ts:47-51   const pendingCount = await count(db, "pending");
                          const conflictCount = await count(db, "conflict");
                          if (conflictCount > 0) return "SYNC_CONFLICT";
                          if (pendingCount > 0) return "PENDING_SYNC";
                          return "SYNCED";
```
`[VERIFIED]`. It counts `"pending"` and `"conflict"` and never `"failed"`.

Worse, `"conflict"` is not a state the queue can be in. The declared union is `> status: "pending" | "failed";` `[VERIFIED] lib/sync-queue.ts:7`, so `conflictCount` is a query for a value nothing writes. `[INFERENCE]` — `count` is a `declare function` with no body (`lib/sync-queue.ts:58`), so I cannot open its implementation, but an index lookup for a status the writer never assigns returns zero on every store I have used. The `SYNC_CONFLICT` branch is dead code, which means the queue has one alarm and it is disconnected.

The scenario, in the field: a technician captures twelve readings in a basement with no signal. `drainQueue` runs, the endpoint returns 502 five times across the backoff schedule `> const RETRY_BACKOFF_MS = [1000, 2000, 5000, 10000, 30000];` (`lib/sync-queue.ts:2`), every entry crosses `MAX_RETRY_COUNT`, all twelve are marked failed. `pendingCount` is now zero. The technician's device displays `SYNCED`. They close the app and drive to the next job. The readings exist nowhere but a dead IndexedDB row, and the spec gate `> Offline capture must survive poor connectivity and retry.` (`spec.md:10`) reports success at the exact moment it failed.

The swallowed error compounds it:
```
lib/sync-queue.ts:40-42   } catch {
                            await incrementRetry(db, entry);
                          }
```
`[VERIFIED]` — a bare `catch` with no binding. The exception object is not merely unlogged, it is unreachable. When these twelve entries fail, nobody can distinguish DNS failure, an expired token, a CORS rejection, and a `JSON.stringify` throw on a circular payload — and the last of those will retry five times and abandon the data no matter how good the connectivity is.

Prescription:
1. `getSyncStatus` must count `"failed"` and return a distinct terminal state; `"SYNCED"` must be reachable only from a zero total. Either implement `"conflict"` or delete the branch — a permanently-false alarm condition trains everyone to trust the reporter.
2. `markFailed` must emit before it returns: entry id, endpoint, final retry count, and the last error's name. That is the identifier set a responder needs to reproduce one instance rather than watch a count rise.
3. Bind the exception (`catch (e)`) and record `e` at warn on each attempt and at error on the terminal one. Log sampling, if it is ever added, must exempt this.
4. The abandoned payload needs somewhere to go — flagged to `eng-data` in `cross_domain`, as the storage decision is theirs; my requirement is only that its existence be observable from outside the device.

## The alert path cannot report its own failure

`runWatchdog` is the repo's only alerting mechanism, and it reports that it alerted without any evidence that it did.

```
lib/notify.ts:25-30   const to = process.env.ALERT_EMAIL?.trim();
                      if (to) {
                        await sendEmail({ to, subject: `${problems.length} job(s) unhealthy` });
                        alerted = true;
                      }
                      return { healthy: problems.length === 0, alerted };
```
`[VERIFIED]`. `alerted = true` is set on the line after the await, unconditionally.

`sendEmail` is documented as, and is, incapable of telling the caller anything:
```
lib/notify.ts:2   * Fire-and-forget: reports errors loudly but never throws, so callers do not fail.
```
`[VERIFIED]`. Its return type is `Promise<void>` (`lib/notify.ts:4`), and all three failure paths return normally: missing key `> console.error("[notify] RESEND_API_KEY unset, dropping mail", payload.subject);` (`lib/notify.ts:7`), non-2xx `> if (!res.ok) console.error("[notify] non-2xx", res.status);` (`lib/notify.ts:17`), and transport/timeout `> console.error("[notify] send failed", e);` (`lib/notify.ts:19`). The comment's "loudly" is the load-bearing falsehood: three `console.error` calls with no logger, no transport, and no destination are the entire telemetry surface of this repository — the grep for `logger|sentry|otel|metric|trace|requestId` across all twelve files returns nothing but these three lines.

Blast radius, concretely: `RESEND_API_KEY` is rotated and the new value does not reach the prod environment. Every watchdog invocation now takes the `if (!key)` branch, returns immediately, and yields `{healthy: false, alerted: true}`. Anything consuming `alerted` — a dashboard, a runbook, an escalation policy — records that the on-call was notified. The damage travels for as long as the rotation goes unnoticed, and the thing that would normally notice it is this function. The `to` branch has the mirror problem: with `ALERT_EMAIL` unset, `runWatchdog` returns `{healthy: false, alerted: false}` having emitted nothing at all — the deployment is silently unmonitored, and no log line marks the moment it became so.

Then the absence question, which is the one my seat exists to ask: **if `runWatchdog` stopped being invoked entirely, what fires?** Nothing. `grep -rn 'runWatchdog' --include='*.ts' .` returns exactly one hit, its own definition at `lib/notify.ts:23` `[VERIFIED]` — there is no caller, no cron, no scheduler entry, and no CI workflow in the repository. Zero problems reported and zero invocations are the same observation to every consumer. This is the two-months-dead nightly job, pre-built.

Prescription, grounded in the rule that a notifier must return its outcome and a scheduled job must prove it ran:
1. `sendEmail` returns a discriminated result (`{ok: true, id}` / `{ok: false, reason}`); `runWatchdog` sets `alerted` from that value, never from reaching the next line. Keep the never-throws property — it is correct — but stop conflating "did not throw" with "delivered."
2. Missing `RESEND_API_KEY` or missing `ALERT_EMAIL` is a startup failure of the alerting path, not a per-call `console.error`. Validate both at boot and fail the health check defined above while either is absent, so the condition is visible without reading stdout.
3. Add a deadman: the watchdog writes a `last_successful_run` timestamp on each completion, and an independent check — one that does not share this process, this deploy, or this API key — alerts when it is older than one and a half scheduled intervals. Every alert this repo can raise currently travels through the single Resend dependency; the deadman must not.
4. Give the alert an actionable identifier. `${problems.length} job(s) unhealthy` (`lib/notify.ts:27`) tells a responder a count and not one job name, tenant, or run id — precisely the "failed to sync, no id" message that turns a page into an archaeology session.
