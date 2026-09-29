by: eng-failure
contributed: [eng-failure]
categories:
  failure_modes: {state: PRESCRIBED, ref: "#captures-die-silently-and-duplicate-on-replay", by: eng-failure, blocking: true}
  invariants:    {state: PRESCRIBED, ref: "#the-distribution-gate-exists-only-in-prose",    by: eng-failure, blocking: true}
  observability: {state: PRESCRIBED, ref: "#the-only-alert-path-reports-success-when-it-sent-nothing", by: eng-failure}
cross_domain:
  - "003_rls_fix.sql is in the directory but not in APPLIED_LEDGER.txt, so production is still running 002's `USING (true)` policy — eng-release owns the ledger gap, eng-authz owns the predicate"
  - "vitest.config.ts include globs are `lib/**/__tests__/**` and `app/**/__tests__/**`; the only test file is at `__tests__/engine.test.ts` and matches neither — eng-test owns whether the classification gate in spec.md §3 runs at all"
  - "drainQueue takes no lock; a page and a service worker draining the same IndexedDB store both POST the same entry — eng-concurrency owns the second-writer case"
  - "rolling 003 back re-grants anon SELECT on every tenant's reports, so the rollback is itself the incident — eng-rollback owns the down path"
  - "RETRY_BACKOFF_MS has no jitter, so every device queued during one outage retries in lockstep at +1s/+2s/+5s — eng-performance owns the herd"

## Captures die silently and duplicate on replay

The offline queue has two exits and the UI is wrong about both.

**Scenario 1 — a capture is lost and the device says everything synced.** A technician captures readings in a basement. Five drain attempts fail. On the sixth pass `drainQueue` takes the terminal branch:

> `if (entry.retryCount >= MAX_RETRY_COUNT) { await markFailed(db, entry.id); continue; }`

`[VERIFIED]` `lib/sync-queue.ts:28-31`. The entry's status becomes `"failed"`. Now the status read:

> `const pendingCount = await count(db, "pending"); const conflictCount = await count(db, "conflict");`

`[VERIFIED]` `lib/sync-queue.ts:47-48`. It counts `"pending"` and `"conflict"` and nothing else. `"conflict"` is never written by any code path — `Entry.status` is declared `"pending" | "failed"` (`[VERIFIED]` `lib/sync-queue.ts:7`, `status: "pending" | "failed";`), and grep across the fixture finds `"conflict"` only at the counter itself. So after the fifth failure `pendingCount` is 0, `conflictCount` is 0, and `getSyncStatus` returns:

> `return "SYNCED";`

`[VERIFIED]` `lib/sync-queue.ts:51`. The technician's readings exist nowhere but that phone, nothing retries them again, and the device displays the same word it displays on success. This is a cache failing *open into wrongness*: the honest answer on this state is an error, and the code returns the reassuring one. Blast radius is the whole job — the report is generated from data that silently isn't there, and the first person to notice is an insurer reading a report with a missing reading, weeks later.

**Scenario 2 — a capture is applied twice.** The POST carries only the payload:

> `body: JSON.stringify(entry.payload),`

`[VERIFIED]` `lib/sync-queue.ts:36`. No idempotency key, though `entry.id` is right there. The server commits, the response is lost on a dropping LTE link, `fetch` rejects, and `catch { await incrementRetry(db, entry); }` (`[VERIFIED]` `lib/sync-queue.ts:40-42`) re-sends the identical body. A `502` from a load balancer that already forwarded the request does the same via the `!response.ok` branch. `[INFERENCE]` on the duplicate itself — I have seen this exact shape produce double-counted readings in every offline-first queue that omits the key, because the client cannot distinguish "not applied" from "applied, ack lost". Duplicated readings then feed `classify()`, which is the input to a report sent to an insurer.

**Prescribe:**
1. `getSyncStatus` must be total over `Entry["status"]` — a `switch` over the union with no default, so adding a state fails to compile rather than reporting `SYNCED`. `"failed"` returns a distinct terminal state that the UI renders as an error the technician must act on. Delete the `"conflict"` count or add `"conflict"` to the union and the code that writes it; a counter for a state nothing produces is dead code that made the bug look handled. (Method #8: make the missing case a compile error, not a silent one.)
2. Send `entry.id` as an `Idempotency-Key` header and have the server key writes on it, returning the original result on replay.
3. `"failed"` is not a terminal state without an operator: name who can re-queue it and how. Today nothing can.

**What would overturn this:** if a caller wraps `getSyncStatus` and separately counts `"failed"` before rendering. No such caller exists in this fixture; `[UNCONFIRMED]` outside it — `grep -rn "getSyncStatus" .` in the real repo settles it.

## The distribution gate exists only in prose

`spec.md:8` states the gate:

> A report may not be distributed unless its verification checklist is complete.

`grep -rniE "checklist|distribut" .` over the whole fixture returns exactly that spec line and the prose in §1. `[VERIFIED]` — there is no checklist column in `001_init.sql` (`reports` is `id`, `tenant_id`, `body`, `created_at`), no checklist field in `schema.prisma`, and no distribution code. The invariant is currently enforced by nobody.

This is the one failure in this repo with no undo: a report sent to an insurer has left the building, and the recovery path is a phone call and a reputation, not a rollback. The prescription is therefore a *database* invariant, not an application check:

- Add `checklist_complete boolean NOT NULL DEFAULT false` and `distributed_at timestamptz` to `public.reports`, plus `CHECK (distributed_at IS NULL OR checklist_complete)`. A code path that forgets the check then cannot write the row.
- The assertion a test can make: for all rows in `reports`, `distributed_at IS NOT NULL` implies `checklist_complete`. Run it as a query, not a unit test, so it also catches writes from psql, an admin tool, or a future service.

`[INFERENCE]`, and this is greenfield — there is nothing to cite because the gate does not exist, which is the finding. Grounded in method #8: a constraint the compiler or the database enforces outranks one a reviewer remembers.

## The only alert path reports success when it sent nothing

`runWatchdog` returns a claim it never verified:

> `await sendEmail({ to, subject: \`${problems.length} job(s) unhealthy\` }); alerted = true;`

`[VERIFIED]` `lib/notify.ts:27-28`. `sendEmail` returns `Promise<void>` and swallows all three of its failure paths — missing key returns early after a `console.error` (`lib/notify.ts:6-9`), a non-2xx only logs (`if (!res.ok) console.error("[notify] non-2xx", res.status);`, `[VERIFIED]` `lib/notify.ts:17`), and a throw is caught and logged (`lib/notify.ts:18-20`). So `alerted: true` means "we attempted", and any consumer treating it as "someone was told" is wrong. When `ALERT_EMAIL` is unset, `alerted` is `false` and *nothing* escalates that the alert channel is unconfigured — the classic absence failure: zero alerts fired looks identical to zero problems.

Credit where due: the outbound call does set `signal: AbortSignal.timeout(10_000)` (`[VERIFIED]` `lib/notify.ts:15`), so a hung Resend cannot pin the watchdog indefinitely. That is the timeout most codebases omit.

**Prescribe:** have `sendEmail` return a discriminated result (`{ok: true} | {ok: false, reason}`) rather than `void`, propagate it into `alerted`, and increment a counter on each failure reason. Separately, alert on *absence*: a heartbeat the watchdog writes on every run, with a monitor that fires when the heartbeat is stale. Both scenarios in `#captures-die-silently-and-duplicate-on-replay` are unbounded in time precisely because nothing here counts.

`/api/health` returns a static literal — `status: "ok"` with a version and a timestamp (`[VERIFIED]` `app/api/health/route.ts:2-6`) — and checks no dependency, so it cannot substitute for this. **eng-observability very likely also answers this category; I am not overwriting them — record both, and defer to their instrumentation shape.**
