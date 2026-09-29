by: eng-observability
contributed: [eng-observability]
categories:
  observability: {state: PRESCRIBED, ref: "#nothing-in-this-repo-can-report-that-it-broke", by: eng-observability, blocking: true}
cross_domain:
  - "003_rls_fix.sql is absent from supabase/APPLIED_LEDGER.txt — eng-release owns whether it was applied; I only claim that nothing detects the drift"
  - "vitest.config.ts include globs never match __tests__/engine.test.ts, so the suite is green on zero tests — eng-test owns it"
  - "002_policies.sql grants anon SELECT/INSERT/UPDATE/DELETE and a USING (true) policy — eng-authz owns the predicate"
  - "drainQueue's markFailed is terminal with no dead-letter or replay path — eng-rollback owns recovery of a technician's abandoned captures"

## Nothing in this repo can report that it broke

Three detection paths exist. All three are structurally incapable of returning a bad answer, and the spec's "Done when — Deploy is repeatable and observable" currently rests on them.

### The health endpoint is a constant, not a check

`[VERIFIED]` `app/api/health/route.ts:2-6`:

```
return Response.json({
    status: "ok",
```

`status` is a string literal. No database round-trip, no migration-version read, no queue-depth read. Concrete scenario: `003_rls_fix.sql` sits unapplied (it is not in `APPLIED_LEDGER.txt`), Postgres is refusing connections, or the Resend key is unset — the probe returns `200 {"status":"ok"}` in all three cases and the uptime monitor stays green. This is the null-result trap: a checker that has never been shown capable of returning non-`ok` is not evidence of health.

**Prescription.** `/api/health` must have at least one dependency assertion that can fail: a `SELECT 1` against the reports table with a ≤2s timeout, and the count of files in `supabase/migrations/` versus lines in `APPLIED_LEDGER.txt`, returning `503` on mismatch. Grounded in the fact that a liveness endpoint returning a literal is indistinguishable from a static file, and a monitor pointed at a static file measures the CDN.

### The watchdog reports that it alerted when it did not

`[VERIFIED]` `lib/notify.ts:26-29`:

```
if (to) {
    await sendEmail({ to, subject: `${problems.length} job(s) unhealthy` });
    alerted = true;
```

`sendEmail` is typed `Promise<void>` and returns normally on every failure path it has: unset key (`lib/notify.ts:7-9` — `console.error("[notify] RESEND_API_KEY unset, dropping mail", payload.subject); return;`), non-2xx (`:17`), and network/abort (`:18-20` — `catch (e) { console.error("[notify] send failed", e); }`). `alerted = true` is set on the *call returning*, not on the mail being accepted.

Concrete scenario: `RESEND_API_KEY` is missing from the production environment after a redeploy. `runWatchdog(["nightly-report-gen"])` returns `{healthy: false, alerted: true}`. Whatever consumes that return value records the page as delivered. Nobody is paged, and the record says somebody was. This is the exact shape of declaring success before the effect is durable — the alerting channel is the one component with no second channel behind it, so its own failure is terminal and silent.

**Prescription.** `sendEmail` returns a discriminated result (`{ok: true, id}` / `{ok: false, reason}`); `alerted` is set only on `ok: true`; a false result increments a counter that the health endpoint exposes. The alert path needs a self-check the alert path is not responsible for reporting.

### No deadman, and no caller

`[VERIFIED]` — `grep -rn "runWatchdog\|drainQueue\|getSyncStatus" .` over the fixture returns only the definition sites in `lib/notify.ts:23` and `lib/sync-queue.ts:23,46`. There is no cron entry, no route, no scheduler config anywhere in the tree (`grep -rni "cron\|schedule" .` returns nothing). `runWatchdog` also takes `problems: string[]` as a parameter — it does not discover problems, so even once invoked it can only report what its absent caller already knew.

Ask the seat question: if report generation silently stops being invoked, which alert fires? None. Error rate stays at zero because the denominator is zero. `[INFERENCE]` — this is the failure I have watched run for two months undetected; "no rows processed" and "not invoked at all" produce identical telemetry, which is none.

**Prescription.** A heartbeat row written on every successful completion of each scheduled job, and an alert on *absence* — "no successful `report-gen` completion in 26h" — evaluated by something outside the app process, so a crashed app cannot suppress its own deadman. 26h, not 24h, so a single slow run does not page.

### The swallow and the unreachable branch

`[VERIFIED]` `lib/sync-queue.ts:40-42`:

```
} catch {
      await incrementRetry(db, entry);
```

The bare `catch` binds nothing and logs nothing. A technician's capture can burn all five backoff attempts and land in `markFailed` (`:28-30`) with zero record of the cause — 502 from a gateway, CORS, a JSON serialisation throw on the payload all look identical afterwards. There is no entry id, tenant id, or endpoint in any log line, so the count on a dashboard could never be traced to a reproducible instance even if it were logged.

Compounding it, `[VERIFIED]` `lib/sync-queue.ts:47-49`:

```
const conflictCount = await count(db, "conflict");
  if (conflictCount > 0) return "SYNC_CONFLICT";
```

`Entry.status` is declared `"pending" | "failed"` (`lib/sync-queue.ts:7`). Nothing in this file writes `"conflict"`. `conflictCount` is always 0 and `SYNC_CONFLICT` is unreachable — a status the UI can render and the system can never produce. `markFailed` entries are also invisible to `getSyncStatus`, which counts only `pending`, so a queue of permanently failed captures reports `"SYNCED"`.

**Prescription.** `catch (e)` with the entry id, endpoint and error name at `warn`, exempt from any sampling; a `failed` count surfaced in `getSyncStatus` so the technician's device does not display `SYNCED` over abandoned work; and either write `"conflict"` somewhere or delete the branch — a dead detection branch is worse than none, because it reads as coverage.

`[UNCONFIRMED]` — whether `console.error` from `lib/notify.ts` reaches a log backend at all depends on the deploy target's stdout capture. The command that settles it: deploy a build with a deliberate `console.error("[notify] canary <uuid>")` and grep the platform's log query for that uuid within 5 minutes. Until that positive control passes, treat every `console.error` in this repo as writing to nowhere.
