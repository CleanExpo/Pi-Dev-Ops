by: eng-failure
contributed: [eng-failure]
categories:
  failure_modes: {state: PRESCRIBED, ref: "#failure-modes-silent-drop-in-the-sync-queue", by: eng-failure, blocking: true}
  observability: {state: PRESCRIBED, ref: "#observability-the-alerting-path-cannot-report-its-own-failure", by: eng-failure, blocking: true}
cross_domain:
  - "two overlapping drainQueue calls read the same pending set and POST the same entry twice — eng-concurrency owns it"
  - "003_rls_fix.sql drops the permissive policy but APPLIED_LEDGER.txt lists only 001 and 002 — eng-release owns whether prod is still world-readable"
  - "vitest.config.ts include globs require lib/**/__tests__ but the only test file is at repo root __tests__/engine.test.ts, so it never runs — eng-test owns it"
  - "the spec's 'verification checklist is complete' gate has no column in schema.prisma or 001_init.sql and no code path anywhere — eng-data owns it"
  - "vitest.config.ts exists with no package.json or lockfile in the repo — eng-supply-chain owns it"

## Failure modes silent drop in the sync queue

The spec's second gate is "Offline capture must survive poor connectivity and retry." The drain loop currently converts poor connectivity into permanent, silent data loss, and the status function is structurally unable to say so.

**Concrete scenario.** A technician on a saturated 4G cell or a site-office captive portal finishes an inspection. `drainQueue` runs.

1. **The first stalled request blocks the whole queue, forever.** The sync `fetch` carries no timeout and the loop awaits each entry in turn. `[VERIFIED]` `lib/sync-queue.ts:27` — `for (const entry of entries) {`; `lib/sync-queue.ts:33-37` — `const response = await fetch(entry.endpoint, {` … with `method`, `headers` and `body` and no `signal`. A captive portal that accepts the TCP connection and never responds leaves that promise pending indefinitely: entries 2..N are never attempted, `retryCount` never increments, backoff never fires, and nothing marks anything failed. The same file's sibling module already knows the fix — `[VERIFIED]` `lib/notify.ts:15` — `signal: AbortSignal.timeout(10_000),` — so this is an omission, not a decision.

2. **Permanent errors are retried, then discarded.** `[VERIFIED]` `lib/sync-queue.ts:38` — `if (!response.ok) await incrementRetry(db, entry);`. A 400 or 422 from a schema-mismatched payload is treated identically to a 503, burns all five backoff slots (~48s of wall clock), and then: `[VERIFIED]` `lib/sync-queue.ts:28-30` — `if (entry.retryCount >= MAX_RETRY_COUNT) {` / `await markFailed(db, entry.id);` / `continue;`. The reading is now in status `failed`, out of the `pending` index, and no code in this repo ever reads it again.

3. **Nobody notices, and the UI actively says the opposite.** `getSyncStatus` counts two things, and neither is `failed`. `[VERIFIED]` `lib/sync-queue.ts:46-51` — `const pendingCount = await count(db, "pending");` / `const conflictCount = await count(db, "conflict");` / `if (conflictCount > 0) return "SYNC_CONFLICT";` / `if (pendingCount > 0) return "PENDING_SYNC";` / `return "SYNCED";`. `"conflict"` is not a member of the status union — `[VERIFIED]` `lib/sync-queue.ts:6` — `status: "pending" | "failed";` — and `grep -rn conflict` over the repo returns only lines 48 and 49, so nothing ever writes it. The `SYNC_CONFLICT` branch is dead code and the `failed` bucket is invisible. The end state is the worst one available: every capture has been destroyed and the device displays **SYNCED**. Answering my seat's question directly — who notices, and how long until they do — the answer is the insurer, at report time, with no local copy left to recover from.

4. **The classification engine has the same fail-open shape.** `[VERIFIED]` `lib/engine.ts:4` — `return { category: 1 };` is the default arm for every unrecognised `source`. An input string the author has not seen (`"blackwater"`, `"sewerage"`, a typo from the capture form) is not rejected — it is silently classified at the *least* severe category and flows into a report distributed to an insurer. `[INFERENCE]` this is the failure I have been paged for most often in classifier code: the default arm is chosen for ergonomics during development and then quietly becomes a correctness decision nobody made.

**Prescriptions** (grounded in the two mechanisms above, not in an external standard — the author may overturn any of them):

- Give the sync `fetch` an explicit timeout. `AbortSignal.timeout(10_000)`, matching `lib/notify.ts:15`, is the defensible starting number because it is the one already chosen in this codebase for an outbound call; it is a prescription, not a measured value.
- Split transport/5xx failure from 4xx. Transport and 5xx retry on the existing backoff; a 4xx is non-retryable and must go straight to a terminal state with the response body recorded, so the payload can be repaired rather than aged out.
- Make `getSyncStatus` total over the status union. Per method #8, the boundary should make this a compile error rather than a runtime silence: switch exhaustively over `Entry["status"]` so adding a `"conflict"` state without handling it fails the build, and either implement `"conflict"` or delete lines 48-49. Today the dead branch reads as coverage that does not exist.
- `markFailed` must be a *visible* terminal state: a distinct UI status ("N captures could not be uploaded") plus a counter, not a row that leaves the pending index. My seat's rule applies — the damage here is unbounded in time precisely because nothing increments an error counter.
- `classify` should not have a silent default. Return an explicit unclassified result the caller must handle, or throw; per method #6 the durable form of this finding is the rule "no total-function default arm in the classification engine", not the one-line correction.

**Method over instinct, one line:** my instinct is to prescribe a dead-letter queue and a circuit breaker; method #1 says the boring version was never tried, and a timeout plus an exhaustive status union closes all four scenarios above without a new subsystem, so that is what I am prescribing.

**What would overturn this** (method #2): a sync endpoint that is proven to answer or reset within a bounded time under captive-portal conditions, plus a surface that already reads the `failed` bucket outside this file. `[UNCONFIRMED]` — I cannot see the caller of `getSyncStatus` from here; `grep -rn "getSyncStatus\|drainQueue" --include=*.ts --include=*.tsx .` in the full application would settle it. Nothing in this fixture calls either function.

## Observability the alerting path cannot report its own failure

Every failure path in this repo terminates in `console.error` and a success-shaped return value. The watchdog that is supposed to be the detection mechanism is itself the least observable component.

1. **`alerted: true` is asserted, not observed.** `[VERIFIED]` `lib/notify.ts:27-28` — `await sendEmail({ to, subject: \`${problems.length} job(s) unhealthy\` });` / `alerted = true;`. `sendEmail` returns `Promise<void>` and cannot fail: `[VERIFIED]` `lib/notify.ts:6-9` — `if (!key) {` / `console.error("[notify] RESEND_API_KEY unset, dropping mail", payload.subject);` / `return;`, and `[VERIFIED]` `lib/notify.ts:17` — `if (!res.ok) console.error("[notify] non-2xx", res.status);`. So on a rotated-out `RESEND_API_KEY`, a 401, or a 429, `runWatchdog` returns `{ healthy: false, alerted: true }`. Any dashboard or caller trusting that field records that an operator was notified when zero mail left the process. The file's own docstring names the intent — `[VERIFIED]` `lib/notify.ts:2` — `* Fire-and-forget: reports errors loudly but never throws, so callers do not fail.` — but "loudly" here means a serverless log line with no counter and no alert attached to it.

2. **The alert call looks dead on arrival.** The Resend POST sets an `authorization` header and no content type: `[VERIFIED]` `lib/notify.ts:13-14` — `headers: { authorization: \`Bearer ${key}\` },` / `body: JSON.stringify(payload),`. The sync client in the same repo does set it — `[VERIFIED]` `lib/sync-queue.ts:35` — `headers: { "content-type": "application/json" },`. `[INFERENCE]` a JSON API receiving a body with no declared content type rejects it at the parse layer; combined with finding 1 that produces a permanent 4xx that is logged once per invocation and reported upward as `alerted: true`. `[UNCONFIRMED]` — one `curl -i -X POST https://api.resend.com/emails -H "authorization: Bearer $RESEND_API_KEY" -d '{}'` against a real key settles whether the header is required; I will not run it from a read-only seat.

3. **`/api/health` cannot fail, so it detects nothing.** `[VERIFIED]` `app/api/health/route.ts:2-6` — `return Response.json({` / `status: "ok",` / `version: process.env.NEXT_PUBLIC_APP_VERSION || "1.0.0",` / `timestamp: new Date().toISOString(),`. It touches no database, no queue, no Resend. An instance with an unreachable Postgres returns 200 and a load balancer or uptime monitor keeps routing production traffic to it. The version fallback compounds it: with `NEXT_PUBLIC_APP_VERSION` unset every build reports `1.0.0`, so the endpoint cannot answer "which build is live" either — which is what the spec's third gate, "Deploy is repeatable and observable," is asking of it.

**Prescriptions:**

- `sendEmail` returns a discriminated result (`{ok: true} | {ok: false, reason}`); `runWatchdog` sets `alerted` from that value and never from control flow. This is the same method #8 boundary fix as the queue status: the current signature makes the lie unrepresentable-in-reverse — there is no value that could carry the failure.
- A missing `RESEND_API_KEY` at boot should fail startup, not degrade to a log line at the moment it is needed. The condition that makes it visible must not be an alert firing.
- `/api/health` distinguishes liveness from readiness: keep the static 200 for liveness, add a readiness path that executes one cheap query against `public.reports` and returns non-200 on failure. Have deploy verification assert `version` equals the commit being deployed rather than accepting the `1.0.0` fallback.
- Alert on **absence**, not rate: the watchdog and the drain both need a "last successful run" heartbeat with a staleness alarm. A watchdog that dies produces zero errors, and an error-rate dashboard looks perfect while nothing is running.

**Overlap declared:** `eng-observability` is dispatched unconditionally and may also answer this category. I am claiming it because the specific defect is a fallback failing *open* into a false success value, which is my lane; where our sections differ, both should be recorded rather than merged away.
