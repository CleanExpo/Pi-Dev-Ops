by: eng-observability
contributed: [eng-observability]
categories:
  observability: {state: PRESCRIBED, ref: "#observability", by: eng-observability, blocking: true}
cross_domain:
  - "003_rls_fix.sql is absent from APPLIED_LEDGER.txt, so 002's `FOR SELECT USING (true)` grant to anon is what is live — eng-release owns the unapplied migration, eng-authz owns the policy"
  - "drainQueue permanently discards a technician's reading at retryCount >= 5 with no server-side record — eng-failure owns the data-loss blast radius"
  - "getSyncStatus reads a `\"conflict\"` status that the `Entry` union cannot hold — eng-contract owns the type/status mismatch; I own only that it makes the state unreachable"
  - "vitest.config.ts include globs are `lib/**/__tests__/**` and `app/**/__tests__/**` but the only test file sits at `__tests__/engine.test.ts` — eng-test owns whether the suite runs at all"

## Observability

The entire telemetry surface of this repository is three `console.error` calls in one file. `grep -rn 'console\.\|logger\|sentry\|metric\|trace\|otel\|heartbeat\|deadman\|cron\|alert'` over the fixture returns only `lib/notify.ts:7`, `:17` and `:19` [VERIFIED]. There is no log sink, no counter, no scheduler and no CI directory in the tree. Spec §3 asserts "Deploy is repeatable and observable" but nothing in the code answers the second half, so every finding below is `PRESCRIBED`, not `DECIDED`.

The question this seat asks — *if this code path silently stopped executing entirely, which specific alert fires, and how long until it does?* — currently has the same answer for every path in this repo: **none, and never.**

### 1. The migration ledger and the migration directory disagree, and nothing compares them

`supabase/APPLIED_LEDGER.txt` contains exactly two lines [VERIFIED]:

```
001
002
```

while `supabase/migrations/` contains `001_init.sql`, `002_policies.sql` and `003_rls_fix.sql` [VERIFIED]. The unapplied file is the one whose own comment says `-- Tenant-scoped replacement for the permissive policy in 002.` [VERIFIED `supabase/migrations/003_rls_fix.sql:1`]. What is therefore live is `002`'s policy:

> `CREATE POLICY "Anon read access" ON public.reports` / `FOR SELECT USING (true);`
> [VERIFIED `supabase/migrations/002_policies.sql:3-4`]

The security consequence belongs to another seat. **The detection failure is mine:** a drift between "migrations we wrote" and "migrations that ran" produces no error, no failed deploy, and no signal of any kind. `/api/health` returns `status: "ok"` while the database is two policies behind the repo. This is the exact shape the seat exists to catch — the state is wrong, and the only thing that would ever tell you is a customer reading another tenant's report.

**Prescribed:** `/api/health` must report the applied-migration head read from the database (`SELECT max(version) FROM supabase_migrations.schema_migrations`, or the ledger's authoritative equivalent), and CI must fail when that head is not equal to the highest-numbered file in `supabase/migrations/`. A drift check that only runs at deploy time is not enough — this drift persists *after* a successful deploy, so it needs a periodic check too. [INFERENCE — mechanism: ledger-as-a-text-file has no transactional relationship to the database that actually ran the DDL, so any hand-edit, partial apply, or aborted deploy desynchronises them silently; I have watched this exact pattern hide an unapplied index for six weeks.]

**Confirm with** [UNCONFIRMED]: `psql "$DATABASE_URL" -c "select version from supabase_migrations.schema_migrations order by version"` against each environment, compared to `ls supabase/migrations/`.

### 2. `runWatchdog` reports that it alerted without any confirmation that it did

`lib/notify.ts:23-31` is the only alerting path in the system, and it sets its own success flag:

> `await sendEmail({ to, subject: \`${problems.length} job(s) unhealthy\` });`
> `alerted = true;`
> [VERIFIED `lib/notify.ts:27-28`]

`sendEmail` returns `Promise<void>` on **every** path — missing key, non-2xx, and thrown exception alike:

> `console.error("[notify] RESEND_API_KEY unset, dropping mail", payload.subject);` / `return;` [VERIFIED `lib/notify.ts:7-8`]
> `if (!res.ok) console.error("[notify] non-2xx", res.status);` [VERIFIED `lib/notify.ts:17`]
> `} catch (e) { console.error("[notify] send failed", e); }` [VERIFIED `lib/notify.ts:18-19`]

Concrete scenario: a new environment is stood up without `RESEND_API_KEY` in its env (nothing in the repo declares it as required — the only references to it are the two lines above). Three jobs go unhealthy. `runWatchdog` returns `{ healthy: false, alerted: true }`. A dashboard reading `alerted` shows the paging path working. No email was sent, no counter incremented, and the one record of the failure is a `console.error` on a serverless invocation nobody ships to a log backend. The file's own docstring — "reports errors loudly but never throws" [VERIFIED `lib/notify.ts:2`] — describes the intent; `console.error` in a Next.js route is not loud, it is a line in a stream with no retention guarantee.

Worse is the branch above it: if `ALERT_EMAIL` is unset, `if (to)` is false, and the function returns `{ healthy: false, alerted: false }` having told absolutely no one, with no log line at all [VERIFIED `lib/notify.ts:25-29`]. Alerting is disabled by a missing environment variable and the disablement is itself silent.

**Prescribed:**
- `sendEmail` returns a discriminated result (`{ok: true} | {ok: false, reason}`), and `alerted` is set from that result, never from the call returning.
- Missing `RESEND_API_KEY` or `ALERT_EMAIL` fails startup (or fails the health check) rather than degrading to a console line — a missing credential on the alerting path is a production incident, not a fallback.
- Every `console.error` here carries the identifier needed to act: which job, which tenant, which run id. `"[notify] non-2xx", res.status` tells an on-call engineer that something failed and nothing about what.
- The alerting path needs its own end-to-end check (a synthetic alert on a schedule that must arrive), because an alerting path that is only exercised during an incident is only tested during an incident.

### 3. `/api/health` is a static literal, and its version field will lie

> `return Response.json({ status: "ok", version: process.env.NEXT_PUBLIC_APP_VERSION || "1.0.0", timestamp: new Date().toISOString() });`
> [VERIFIED `app/api/health/route.ts:2-6`]

This endpoint returns `ok` without touching the database, the queue, or the migration head. It proves one thing: a Node process is accepting connections. It will return 200 with the database unreachable, with `003` unapplied, and with the watchdog not having run for a month.

The `|| "1.0.0"` default is the sharper problem. Nothing in this tree sets `NEXT_PUBLIC_APP_VERSION`, so the endpoint reports `1.0.0` for every build ever deployed [VERIFIED — `grep -rn 'NEXT_PUBLIC_APP_VERSION'` matches only `app/api/health/route.ts:4`]. At 3am, after a rollback, the single question is "is the old build live yet?" and this endpoint answers it with a plausible-looking number that is not derived from the build at all. A field that is wrong is worse than a field that is absent, because it gets believed.

**Prescribed:** health returns `status: "degraded"` with a named reason when the DB round-trip fails or the migration head is behind; `version` is the immutable build SHA injected at build time, and the fallback is `"unknown"` — never a value shaped like a real version. Add `last_watchdog_completed_at` to the payload so the deadman in §4 has something to read.

### 4. Nothing detects absence of invocation; the offline queue fails in total silence

`runWatchdog` has no caller and no scheduler anywhere in the tree — no cron definition, no CI workflow, no queue consumer [UNCONFIRMED — confirm against the real repo with `grep -rn 'runWatchdog\|schedule\|cron' --include='*.ts' --include='*.json' --include='*.yml' .` and `ls .github/workflows`]. If it were wired up and then stopped being invoked, error rate stays at zero because zero runs produce zero errors, and no alert exists that fires on *silence*.

The client half is equally dark. `drainQueue` swallows every network exception with a bare, un-logged catch:

> `} catch { await incrementRetry(db, entry); }`
> [VERIFIED `lib/sync-queue.ts:40-42`]

and at the retry ceiling it discards the reading:

> `if (entry.retryCount >= MAX_RETRY_COUNT) { await markFailed(db, entry.id); continue; }`
> [VERIFIED `lib/sync-queue.ts:28-31`]

Concrete scenario: a technician captures readings in a basement, the endpoint returns 502 for the duration of an incident, five backoff attempts elapse (1s + 2s + 5s + 10s + 30s — under a minute of wall clock, per `RETRY_BACKOFF_MS` at `lib/sync-queue.ts:2` [VERIFIED]), and the job is marked `failed` on the device. The server never learns the capture existed. Spec §2 requires "Offline capture must survive poor connectivity and retry" — it survives for 48 seconds, and its death is unobservable from the server side.

The one indicator that might have surfaced this is structurally dead: `getSyncStatus` counts `"conflict"` —

> `const conflictCount = await count(db, "conflict");`
> [VERIFIED `lib/sync-queue.ts:48`]

— but `Entry.status` is declared `"pending" | "failed"` [VERIFIED `lib/sync-queue.ts:7`]. No entry can ever hold `"conflict"`, so `conflictCount` is always 0 and `"SYNC_CONFLICT"` is unreachable. The UI has a conflict state it can never enter. Note also that `getSyncStatus` counts only `pending` and `conflict` — entries in `failed`, the ones that were actually lost, are invisible to it, so a device with five dropped captures reports `"SYNCED"`.

**Prescribed:**
- A deadman on the watchdog: an external check that fails when `last_watchdog_completed_at` is older than one and a half intervals. Alerting on error rate alone cannot see a job that stopped being called.
- `catch` at `sync-queue.ts:40` logs at warn with the entry id, endpoint and attempt number, and increments a counter. A retry that is invisible is indistinguishable from a success.
- Every transition to `failed` posts a permanent-failure beacon to the server (best-effort, separate endpoint) carrying entry id, tenant and last error, so dropped captures are countable server-side. Today the only person who can observe data loss is the technician, and only if they look.
- Fix `getSyncStatus` to include `failed` in its result, and either populate `"conflict"` or delete the branch — a status the code cannot produce is a monitoring line that reads healthy by construction.
- Log sampling, if it is ever introduced, must exempt error-level events. [INFERENCE — the failure here is rare-error-in-hot-path: a uniform sample rate removes exactly the events you needed.]

**Blocking** because §1 hides a live tenant-isolation defect behind a green health check, and §2 means the system's only alerting path can report success while sending nothing. Both must be resolved before this becomes code.
