by: eng-failure
contributed: [eng-failure]
categories:
  failure_modes: {state: PRESCRIBED, ref: "#offline-queue-drops-captures-and-reports-synced", by: eng-failure, blocking: true}
  migration:     {state: PRESCRIBED, ref: "#migration-003-half-applies-and-both-halves-are-silent", by: eng-failure, blocking: true}
  invariants:    {state: PRESCRIBED, ref: "#distribution-gate-has-no-invariant-that-survives-a-retry", by: eng-failure, blocking: true}
cross_domain:
  - "two overlapping drainQueue runs re-POST the same entries and no idempotency key exists — eng-concurrency owns it"
  - "runWatchdog returns alerted: true without knowing the mail sent, and alerts nobody at all when ALERT_EMAIL is unset — eng-observability owns it"
  - "003 sits in the migrations directory but not in APPLIED_LEDGER.txt — eng-release owns the ledger divergence"
  - "the tenant predicate in 003 depends on public.user_tenant_access, which no migration creates — eng-authz owns the predicate"
  - "the vitest include globs never match __tests__/engine.test.ts, so the classification test does not run — eng-test owns it"
  - "AuditLog cascades from Inspection which cascades from User, so deleting a user erases the audit trail — eng-data owns it"

## Offline queue drops captures and reports SYNCED

The queue's terminal state is indistinguishable from success, so a technician's readings are destroyed and the UI congratulates them.

Concrete scenario: a technician captures 40 readings in a basement with a captive-portal wifi that answers every POST with a 502. Each entry retries five times over ~48s of backoff, then `if (entry.retryCount >= MAX_RETRY_COUNT) await markFailed(db, entry.id)` [VERIFIED] `lib/sync-queue.ts:28-29`. `markFailed` moves the row out of the `pending` index. `getSyncStatus` then computes `const pendingCount = await count(db, "pending")` → 0, and `if (pendingCount > 0) return "PENDING_SYNC"; return "SYNCED"` [VERIFIED] `lib/sync-queue.ts:47,50-51`. Nothing counts `failed`. The technician drives away.

The one branch that could have caught it is unreachable: `const conflictCount = await count(db, "conflict")` [VERIFIED] `lib/sync-queue.ts:48`, but the type is `status: "pending" | "failed"` [VERIFIED] `lib/sync-queue.ts:7` and no code path writes `"conflict"` — grep over the fixture returns only that one line. `SYNC_CONFLICT` is dead code that reads like a safety net.

Three compounding defaults, each decided silently:

- **No timeout on the sync fetch.** `const response = await fetch(entry.endpoint, {...})` [VERIFIED] `lib/sync-queue.ts:33-37` carries no `signal`. The drain is a sequential `for (const entry of entries)` [VERIFIED] `lib/sync-queue.ts:27`, so one socket that opens and never responds — the ordinary behaviour of a captive portal or a carrier-grade NAT dropping an idle connection — stalls every remaining entry indefinitely, with no error, no retry increment, and no timer. That this is an oversight rather than a policy is visible from the sibling module, which does set one: `signal: AbortSignal.timeout(10_000)` [VERIFIED] `lib/notify.ts:15`.
- **No 4xx/5xx distinction.** `if (!response.ok) await incrementRetry(db, entry)` [VERIFIED] `lib/sync-queue.ts:38`. A 422 from a schema change burns all five attempts on a payload that will never be accepted, then silently discards it — the fastest path to the data loss above is a server-side validation change, not an outage.
- **No jitter.** `const RETRY_BACKOFF_MS = [1000, 2000, 5000, 10000, 30000]` [VERIFIED] `lib/sync-queue.ts:2`, fixed and identical on every device. A fleet that loses connectivity together — a regional carrier blip, or simply a crew leaving a site at 5pm — retries in lockstep at t+1s, +2s, +5s. [INFERENCE] the mechanism is synchronised backoff without decorrelation; I have watched it convert a 30-second dependency brownout into a 20-minute one because each recovery attempt was immediately re-flattened by the whole fleet arriving at once.

Prescription, grounded in the spec's own gate — `Offline capture must survive poor connectivity and retry`:

1. `failed` is a state the human must see. `getSyncStatus` returns `SYNCED` only when `pending`, `failed` and `conflict` are all zero; a non-zero `failed` count surfaces as a blocking banner naming the count and the oldest capture's timestamp. Nothing is ever removed from IndexedDB by retry exhaustion — only by a 2xx, or by an explicit human discard.
2. `AbortSignal.timeout` on the sync fetch, budget stated as a number in the module (10s matches `notify.ts`; pick deliberately, do not inherit). A timeout increments `retryCount` on the same path as a network throw.
3. Full-jitter backoff: sleep a random value in `[0, base]` rather than `base`.
4. 4xx other than 408/429 is terminal — mark it `failed` immediately rather than retrying five times, and record the response status on the entry so the banner can say *why*.
5. Wrap the loop body so one `put`/`markFailed` rejection (IndexedDB quota is the realistic one) does not abandon entries `k+1..N` for the rest of the session.

**Blocking**: the failure is silent, unbounded in time, and destroys the only copy of field data.

## Migration 003 half applies and both halves are silent

`003_rls_fix.sql` is three statements whose ordering makes every partial outcome wrong, and both wrong outcomes present as normal application behaviour rather than as an error.

The statements are `DROP POLICY IF EXISTS "Anon read access"`, then `CREATE POLICY reports_tenant_select ... USING (tenant_id IN (SELECT tenant_id FROM public.user_tenant_access WHERE user_id = auth.uid()))`, then `REVOKE ALL ON public.reports FROM anon` [VERIFIED] `supabase/migrations/003_rls_fix.sql:2,4-6,7`. `public.user_tenant_access` is created by no migration in this repo — the only `CREATE TABLE` anywhere is `CREATE TABLE public.reports` [VERIFIED] `supabase/migrations/001_init.sql:1`, and grep for `user_tenant_access` returns exactly the one line in 003. So `CREATE POLICY` resolves a relation that does not exist and raises.

Two outcomes, and which one you get is decided by a migration-runner flag nobody in this repo has stated:

- **Runner wraps the file in a transaction** (Supabase CLI default). 003 aborts and rolls back. Production keeps `FOR SELECT USING (true)` plus `GRANT SELECT, INSERT, UPDATE, DELETE ON public.reports TO anon, authenticated` [VERIFIED] `supabase/migrations/002_policies.sql:4,6`. This is the fail-open case: the tenancy fix appears in the repo, the reviewer sees it, and every tenant's reports stay readable and writable by `anon`. `APPLIED_LEDGER.txt` contains only `001` and `002` [VERIFIED] `supabase/APPLIED_LEDGER.txt:1-2`, which is consistent with this having already happened.
- **Runner does not stop on error** (`psql` without `ON_ERROR_STOP=1`, the common hand-run). DROP succeeds, CREATE fails, REVOKE succeeds. `reports` now has RLS enabled and **zero** SELECT policies. Postgres default-denies. Every authenticated read returns **zero rows with no error** — the application does not 500, it renders "no reports". [INFERENCE] this is the mechanism I would bet on being mistaken for a data-loss incident: the on-call engineer's first hypothesis is that the reports table was truncated, not that a policy is missing, and the health endpoint agrees with them by returning `status: "ok"` unconditionally [VERIFIED] `app/api/health/route.ts:2-3`.

Prescription:

1. 003 does not ship until the migration that creates `public.user_tenant_access` ships **before** it, in the same deploy, with the ledger proving both applied.
2. Order the statements so no window exists with RLS on and no policy: `CREATE POLICY reports_tenant_select` under a new name **first**, verify, then `DROP POLICY "Anon read access"`, then `REVOKE`. A rename-then-drop is strictly safer than a drop-then-create for anything that default-denies.
3. Every migration file runs under an explicit single transaction, and the runner asserts non-zero exit on error. State this once, in the runner config, not per-file.
4. A post-apply assertion that fails the deploy: `SELECT count(*) FROM pg_policies WHERE tablename='reports' AND cmd='SELECT'` must be exactly 1, and a query as `anon` against `public.reports` must return 0 rows *and* the `authenticated` fixture must return >0. [UNCONFIRMED] I cannot run these from a read-only review; the exact command a human should run before merge is `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/migrations/003_rls_fix.sql` against a scratch branch and observe whether it errors.

**Overlap, declared rather than hidden**: eng-release owns the ledger disagreeing with the directory, and eng-authz owns whether the predicate itself is correct. My claim on `migration` is narrower and different from both — it is what state the database is left in *during and after a failed apply*, and that neither resulting state announces itself.

**Blocking**: one branch is a cross-tenant data exposure that is live today; the other is a silent total read outage.

## Distribution gate has no invariant that survives a retry

The spec states the gate — `A report may not be distributed unless its verification checklist is complete` — and nothing in the repository implements it. Grep for `distribut`, `checklist`, `insurer` and `verif` across every file returns hits only in `spec.md:5,8` [VERIFIED]; there is no distribution route, no `distributed` column in `CREATE TABLE public.reports` [VERIFIED] `supabase/migrations/001_init.sql:1-6`, and no model for it in `lib/schema.prisma`. This is greenfield, so the finding is about the shape the invariant must take, not about code I can cite.

Stated as one condition and two assertions someone can test, because "the gate is checked" is not testable and "the gate holds under partial failure" is:

- **A1** — no row of `reports` has `distributed_at IS NOT NULL` while its checklist is incomplete. Enforceable in the database, not only in the handler: a `CHECK` or a trigger, so a backfill script, a support engineer with a psql session, or a second service cannot bypass it.
- **A2** — for any report, the count of documents delivered to an insurer is exactly 1 across the report's whole lifetime, including every retry, every redeploy mid-request, and every duplicate click.

A2 is the one that will actually be violated, and this is my lane. [INFERENCE] the mechanism: distribution is inherently a multi-step write — check the checklist, call the insurer's endpoint, mark the row distributed. Whatever the order, one crash point is unrecoverable without design:

- Mark-then-send: the process dies after the row is marked. The insurer never received the report, the system believes it did, and nothing retries because the row no longer looks pending. Silent non-delivery of a legal document.
- Send-then-mark: the process dies after the insurer accepted it. Any retry — an operator retry, a queue redelivery, a user refreshing — sends a **second** report. This one is not fixable after the fact: an email or an API POST to an external party cannot be un-sent, and the blast radius is the insurer's system and the customer relationship, not ours.

Prescription:

1. Distribution is a two-phase record, never a single handler. Write an outbox row (`report_id`, `idempotency_key`, `state=pending`) inside the same transaction that verifies the checklist, then have a separate worker perform the send and transition to `sent`. The transaction boundary is what makes A1 and A2 hold together.
2. The `idempotency_key` is derived deterministically from the report id and content version, sent on the outbound call, and unique-constrained locally. A retry with the same key is a no-op at both ends. [UNCONFIRMED] whether the insurer's endpoint honours an idempotency header is unknown from here and must be confirmed against their API docs before choosing between "they dedupe" and "we must never send twice".
3. An explicit timeout and a bounded retry budget on the outbound call, with the ambiguous outcome — timeout after the request was written to the socket — treated as *possibly sent*, requiring reconciliation against the insurer rather than a blind resend.
4. An invariant check that runs on a schedule, not only in tests: rows in `sent` with no delivery receipt, and rows in `pending` older than the retry budget, are both alertable conditions. Alert on the **presence of stuck rows and on the absence of any transition in N minutes** — a worker that dies entirely produces zero errors, and an error-rate dashboard looks perfect while nothing is running.

**Blocking**: this must be settled before the distribution path is written, because retrofitting exactly-once onto a handler that already sends is a data-migration problem plus an apology to an insurer.
