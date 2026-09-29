by: eng-failure
contributed: [eng-failure]
categories:
  failure_modes: {state: PRESCRIBED, ref: "#silent-data-loss-in-the-offline-sync-queue", by: eng-failure, blocking: true}
  rollback:      {state: PRESCRIBED, ref: "#migration-003-has-no-recovery-from-its-own-mid-file-abort", by: eng-failure, blocking: true}
  observability: {state: PRESCRIBED, ref: "#nothing-in-this-system-reports-absence", by: eng-failure, blocking: true}
cross_domain:
  - "migration 003 was merged but never applied, so production still runs the 002 `USING (true)` policy with GRANT to anon — eng-authz owns the tenancy breach, eng-release owns the ledger drift"
  - "vitest `include` is `lib/**/__tests__/**` and `app/**/__tests__/**`, but the only test file is at repo-root `__tests__/engine.test.ts`; the gate the spec's third Done-when relies on collects nothing — eng-test owns whether that fails red or passes vacuously"
  - "the spec's distribution gate has no representation in the schema — `public.reports` is (id, tenant_id, body, created_at) with no checklist state, so 'may not be distributed unless complete' is enforced by nothing — eng-data owns the column, whoever owns `invariants` owns the assertion"
  - "003 references `public.user_tenant_access`, which no migration creates — eng-data owns the missing table"

## Silent data loss in the offline sync queue

The spec's second gate is the one this code exists to satisfy:

> Offline capture must survive poor connectivity and retry.

The queue survives *no* connectivity. It does not survive *poor* connectivity, which is the harder and more common case, and the failure is silent in both directions.

**No timeout on the outbound fetch.** `[VERIFIED]` `lib/sync-queue.ts:33-37` constructs the request with no `signal`:

```
      const response = await fetch(entry.endpoint, {
        method: "POST",
        headers: { "content-type": "application/json" },
```

`[VERIFIED]` The same repo already knows how to do this — `lib/notify.ts:15` passes `signal: AbortSignal.timeout(10_000),`. The omission here is a decision nobody recorded. `[INFERENCE]` A TCP connection that opens and then stalls — the standard behaviour of a site trailer on a marginal cellular link, and of any captive portal that has swallowed the SYN — leaves that `await` pending with no upper bound. The loop is serial, so entry 1 blocks entries 2..N indefinitely. The device reports `PENDING_SYNC` and the technician drives away. I have watched this exact shape strand an entire day of field captures behind one hung request.

**A captive portal deletes the capture.** `[INFERENCE]` Hotel, airport and depot Wi-Fi portals answer any POST with a 200 and an HTML login page. `response.ok` is `true`, so `lib/sync-queue.ts:39` runs `await removeEntry(db, entry.id);`. The only copy of the reading is deleted from IndexedDB and the server never saw it. Nothing distinguishes "the server accepted this" from "something on the path answered 200". This is the failure that costs a real inspection.

**Partial drain with no resume point.** `[VERIFIED]` `lib/sync-queue.ts:29` calls `await markFailed(db, entry.id);` outside any `try`. If that write rejects — `QuotaExceededError`, or the browser evicting the IndexedDB transaction while the tab is backgrounded — `drainQueue` throws at item *k*. `[INFERENCE]` Items 1..k-1 are applied, k+1..N are untouched, and nothing anywhere records where it stopped. `[INFERENCE]` No caller of `drainQueue` exists in this repo (`grep -rn "drainQueue" --include="*.ts"` returns only the definition), so whatever calls it from a service worker or a visibility handler is presumed to have no `.catch` — a rejected promise from a fire-and-forget drain is unobserved by construction.

**Duplicate submission on a write failure.** `[VERIFIED]` The `try` at `lib/sync-queue.ts:32-42` wraps the IndexedDB writes as well as the fetch, so when `removeEntry` rejects *after* a successful POST, the `catch` runs `await incrementRetry(db, entry);` — the delivered entry stays `pending` and is POSTed again on the next drain. The server needs to be idempotent for this and no key exists in the payload contract to make it so.

**Prescription**

1. Pass `signal: AbortSignal.timeout(N)` on the drain fetch; `N` is a decision, not a default. Grounded in `lib/notify.ts:15` already choosing 10s for a less critical path.
2. Make the client require positive proof of acceptance — a specific status plus a parsed response body carrying the server-assigned id — before `removeEntry`. Treat a 2xx that does not parse as a retry, not a success. This is the only thing that closes the captive-portal hole.
3. Give every entry a client-generated idempotency key sent on the POST, so re-delivery after a failed local write is a server-side no-op rather than a duplicate reading.
4. Wrap each entry's processing in its own `try`, so one entry's local-write failure cannot abort the pass; count and surface the failures rather than propagating them.
5. Add jitter to `RETRY_BACKOFF_MS` (`lib/sync-queue.ts:2`). `[INFERENCE]` The array is fixed and shared, so every device that lost the server at the same moment retries at the same 1s/2s/5s marks. When the server comes back, the whole fleet lands together and knocks it down again.

**What would overturn this:** if the sync endpoint is behind a gateway that already enforces a hard request deadline and rejects non-idempotent replays by key, items 1 and 3 collapse to "document it". Point me at that config and I'll drop them.

## Migration 003 has no recovery from its own mid-file abort

Ask the seat question of the one migration that has not run yet.

`[VERIFIED]` `supabase/APPLIED_LEDGER.txt` contains `001` and `002` only, so `003_rls_fix.sql` is still ahead of production. `[VERIFIED]` Its first statement is destructive and its second cannot succeed:

`supabase/migrations/003_rls_fix.sql:2` — `DROP POLICY IF EXISTS "Anon read access" ON public.reports;`
`supabase/migrations/003_rls_fix.sql:6` — `USING (tenant_id IN (SELECT tenant_id FROM public.user_tenant_access WHERE user_id = auth.uid()));`

`[VERIFIED]` `grep -rn "CREATE TABLE" supabase/` returns exactly one hit, `001_init.sql:1`, for `public.reports`. `public.user_tenant_access` is created by no migration in this repo.

`[INFERENCE]` So the `CREATE POLICY` fails on a missing relation. If the runner wraps each file in a transaction the whole file rolls back and the deploy is merely red — recoverable. If it does not, and plenty of runners do not, the end state is: the permissive policy dropped, no replacement policy created, `REVOKE` at line 8 never reached, RLS still enabled from `002_policies.sql:1`. **RLS enabled with zero SELECT policies means every authenticated read of `public.reports` returns zero rows.** Report distribution to insurers stops completely, and it stops looking like an empty result set rather than an error — the application will render "no reports" and log nothing.

There is no down path. `[VERIFIED]` The migrations directory holds three forward files and nothing else (`ls supabase/migrations/`), and `DROP POLICY` is not reversed by re-running 003. At 3am the operator's only route is to hand-write the 002 policy back into production out of version control, which is how the ledger drifted in the first place.

**Prescription**

1. Do not ship 003 until the migration that creates `public.user_tenant_access` is ordered before it. A migration referencing a table that does not exist is a deploy-time failure disguised as a security fix.
2. Assert the runner wraps each file in a single transaction, and prove it by running 003 unmodified against a scratch database and confirming the 002 policy is still present afterwards. `[UNCONFIRMED]` — a human runs `supabase db reset && supabase migration up` against a local stack and then `SELECT polname FROM pg_policy WHERE polrelid = 'public.reports'::regclass;`. I cannot execute this.
3. Ship a `004_rollback_003.sql` that recreates a known-good tenant-scoped policy, so the recovery sequence is "apply 004", not "remember what 002 said".
4. Add a post-migration assertion that `public.reports` has at least one `SELECT` policy and that a seeded authenticated user can read their own row. A zero-policy table is indistinguishable from a correctly-secured one until a customer reports missing data.

Note: eng-rollback and eng-release are both dispatched here and will answer `rollback` and `migration` too. I am claiming the blast radius of the *partial* application specifically; where we differ, I hold that the un-transacted case is the one to design for.

## Nothing in this system reports absence

Every detection path here reports rates, and every one of them goes quiet in exactly the state that matters.

**`getSyncStatus` is structurally incapable of reporting a stranded capture.** `[VERIFIED]` `lib/sync-queue.ts:46-52` counts two statuses:

```
  const pendingCount = await count(db, "pending");
  const conflictCount = await count(db, "conflict");
```

`[VERIFIED]` The `Entry` type at `lib/sync-queue.ts:7` is `status: "pending" | "failed";` — `"conflict"` is not a value this queue ever writes, so `conflictCount` is permanently 0 and `SYNC_CONFLICT` is dead code. `"failed"`, which `markFailed` at line 29 sets after `MAX_RETRY_COUNT` attempts, is counted by nothing. `[INFERENCE]` The consequence is exact: a capture that exhausts all five retries becomes `failed`, drops out of `pendingCount`, and `getSyncStatus` returns `"SYNCED"`. The technician's device tells them the reading uploaded at the precise moment it has permanently given up. This is a fallback that fails open into wrongness, and it fails open toward the reassuring answer.

**The watchdog no-ops on an unset environment variable and reports success-shaped output.** `[VERIFIED]` `lib/notify.ts:25-30`:

```
  const to = process.env.ALERT_EMAIL?.trim();
  if (to) {
    await sendEmail({ to, subject: `${problems.length} job(s) unhealthy` });
```

If `ALERT_EMAIL` is unset or whitespace, no alert is sent, the function returns normally, and the only trace is `alerted: false` in a return value. `[VERIFIED]` One layer down, `lib/notify.ts:5-9` does the same for the credential — missing `RESEND_API_KEY` produces a `console.error` and a `return`. `[VERIFIED]` The file's own docstring at line 2 states the intent: `reports errors loudly but never throws, so callers do not fail.` `[INFERENCE]` "Loudly" here means `console.error` in a server process, which in most Next.js hosting is an unindexed log line nobody has an alert on. The alerting system can be entirely dark in production and the only symptom is silence, which is also what healthy looks like.

**`/api/health` cannot fail.** `[VERIFIED]` `app/api/health/route.ts:2-6` returns `status: "ok"` unconditionally — it checks no database, no queue, no migration state. `[INFERENCE]` An uptime monitor pointed at it stays green through the total read outage described in the section above, because the route never touches `public.reports`.

**Prescription**

1. `getSyncStatus` must return a distinct terminal state derived from `count(db, "failed")`, and the client must surface it as a blocking condition before a technician can leave a site. Either delete `"conflict"` or add it to the `Entry` union and write it — a status counted but never written is a check that can only ever pass.
2. `runWatchdog` must fail closed on missing configuration: absent `ALERT_EMAIL` or `RESEND_API_KEY` is a startup error, not a runtime shrug. A watchdog that cannot alert should refuse to start rather than run silently.
3. Alert on the *absence* of a successful drain — "no sync completed in the last N hours across the fleet" — not on the error rate. A queue that has stopped running entirely emits zero errors and looks perfect on any rate dashboard.
4. Make `/api/health` execute one cheap authenticated `SELECT` against `public.reports` so a zero-policy table turns the probe red.
5. Per method principle 6: items 1 and 2 are the same review comment twice, so the durable fix is a lint rule banning a bare `console.error` in a catch on any path whose job is notification. Write the rule, not the two corrections.

**What would overturn this:** if there is a platform-level log drain with an alert on `[notify]` and on absence of drain completions, items 2 and 3 are already handled and I would withdraw them. I found no such configuration in this repo.
