by: eng-observability
contributed: [eng-observability]
categories:
  observability:      {state: PRESCRIBED, ref: "#nothing-here-fires-when-a-code-path-stops-running", by: eng-observability, blocking: true}
  invariants:         {state: PRESCRIBED, ref: "#two-functions-report-success-that-did-not-happen", by: eng-observability, blocking: true}
  interface_contract: {state: PRESCRIBED, ref: "#sendemail-discards-the-only-outcome-anyone-needs-to-record", by: eng-observability}
cross_domain:
  - "migration 003 exists on disk but not in the applied ledger — eng-release owns whether it ran"
  - "a queue entry that exhausts 5 retries is dropped with the technician's readings still on the device — eng-failure owns the blast radius"
  - "003 replaces a USING (true) SELECT policy; until it applies, tenant isolation is off — eng-authz owns the predicate"
  - "vitest.config.ts includes lib/**/__tests__ and app/**/__tests__, but the only test file is at ./__tests__ — eng-test owns whether any test runs at all"

## Nothing here fires when a code path stops running

Ask the seat question — *if this path silently stopped executing, which alert fires and how long until it does?* — and the answer for every path in this repo is "none, ever". Three independent reasons, each verified.

**The watchdog has no invoker.** `runWatchdog` is exported and never called. `[VERIFIED]` `grep -rn -E "runWatchdog|drainQueue|getSyncStatus" .` over the whole fixture returns only the three `export async function` definition lines — `lib/notify.ts:23` `export async function runWatchdog(problems: string[]) {`, `lib/sync-queue.ts:23`, `lib/sync-queue.ts:46` — and zero call sites. It also takes `problems` pre-computed by a caller that does not exist, so even wired up it reports on whatever the caller chose to look at, never on the caller's own absence.

**The health endpoint attests to nothing.** `[VERIFIED]` `app/api/health/route.ts:3` — `status: "ok",` is a string literal. The handler opens no database connection, reads no ledger, inspects no queue. `[VERIFIED]` `app/api/health/route.ts:4` — `version: process.env.NEXT_PUBLIC_APP_VERSION || "1.0.0",` falls back to a hardcoded version, so the endpoint cannot even tell you which build answered. Concrete scenario: deploy lands, migration 003 does not apply (`[VERIFIED]` `supabase/APPLIED_LEDGER.txt` contains only `001` and `002` while `supabase/migrations/003_rls_fix.sql` exists on disk), the permissive `[VERIFIED]` `supabase/migrations/002_policies.sql:4` — `FOR SELECT USING (true);` — stays live, and `/api/health` returns 200 `{"status":"ok"}` forever. Every uptime monitor and load-balancer probe pointed at it is green while cross-tenant reads are open. Spec §3 says *"Deploy is repeatable and observable"*; the only observation surface in the repo is a constant.

**There is no place for a signal to go.** `[VERIFIED]` `ls -a` on the fixture root lists exactly `__tests__ app lib spec.md supabase vitest.config.ts` — no `package.json`, no CI workflow, no deploy manifest, no log/metric client. `[VERIFIED]` `grep -rn -E "logger|Sentry|metric|heartbeat|cron|schedule"` matches nothing; the only telemetry in the codebase is three `console.error` calls in `lib/notify.ts`.

Prescribed, grounded in the failure this class of system produces — a nightly job that stopped two months ago and produced no log line because "nothing processed" emits nothing:

1. A **deadman** on report distribution and on queue drain, alerting on *absence*: "no successful `drainQueue` completion recorded in 26h" and "no report distributed in 26h". Alerting on error rate cannot fire here — zero errors out of zero runs is the exact shape of this outage.
2. `/api/health` must execute a real read against `public.reports` and compare `supabase/migrations/*.sql` against `APPLIED_LEDGER.txt`, returning non-200 on drift. A liveness probe that cannot fail is worse than no probe, because it converts an outage into a green dashboard.
3. Every alert channel needs a self-test that proves the channel itself is alive, not just the thing it watches — see the next section for why this one currently cannot be trusted.

`[INFERENCE]` on the prescription, `[VERIFIED]` on every claim about what the code does.

## Two functions report success that did not happen

Both attestation bugs are statable as assertions a test could run today, and both are the seat-file failure mode "success declared before the effect is durable".

**`alerted: true` when the mail was dropped.** `[VERIFIED]` `lib/notify.ts:7` — `console.error("[notify] RESEND_API_KEY unset, dropping mail", payload.subject);` — then `return;`. `sendEmail` is `Promise<void>` and swallows this, so `[VERIFIED]` `lib/notify.ts:28-29`:

```
    await sendEmail({ to, subject: `${problems.length} job(s) unhealthy` });
    alerted = true;
```

sets `alerted = true` unconditionally. Concrete scenario: `RESEND_API_KEY` is missing from one environment — the single most common env-var drift there is — every alert is dropped to stderr, and `runWatchdog` returns `{healthy: false, alerted: true}` to whatever records it. The system's own record says the page went out. The same holds for the non-2xx branch, `[VERIFIED]` `lib/notify.ts:17` — `if (!res.ok) console.error("[notify] non-2xx", res.status);` — a 429 from Resend is indistinguishable from a delivered alert.

Assertion: **`runWatchdog` must never return `alerted: true` unless the provider returned 2xx.** Prescription: `sendEmail` returns a discriminated result; `runWatchdog` sets `alerted` from it; a dropped alert is itself an alertable condition on a second, independent channel.

**`"SYNCED"` when the readings are permanently stuck.** `[VERIFIED]` `lib/sync-queue.ts:7` — `status: "pending" | "failed";`. `getSyncStatus` counts neither of the states that matter: `[VERIFIED]` `lib/sync-queue.ts:48` — `const conflictCount = await count(db, "conflict");` — `"conflict"` is not a member of the `Entry.status` union, so `conflictCount` is structurally always 0 and `[VERIFIED]` `lib/sync-queue.ts:49` — `if (conflictCount > 0) return "SYNC_CONFLICT";` — is unreachable. Nothing counts `"failed"`. Concrete scenario: a technician captures readings in a basement, five drain attempts fail, `[VERIFIED]` `lib/sync-queue.ts:29` — `await markFailed(db, entry.id);` — moves the entry out of `pending`, `pendingCount` drops to 0, and `getSyncStatus` returns `"SYNCED"`. The technician drives away. Spec §2 requires *"Offline capture must survive poor connectivity and retry"*; the status function actively certifies the case where it did not.

Assertion: **`getSyncStatus` must never return `"SYNCED"` while any entry is in `failed`.**

Compounding both: `[VERIFIED]` `lib/sync-queue.ts:40` — `} catch {` — a bare catch with no binding, no log, no counter, wrapping the `fetch` at line 33. The non-2xx branch at line 38 emits nothing either. Every retry and every permanent failure in the offline path is invisible on the device *and* on the server, because this runs against IndexedDB in the browser and never reports upstream. Prescribe a counter per outcome (`ok` / `retry` / `exhausted`), each carrying the entry id and tenant, flushed to the server on the next successful drain — otherwise the count rises on nobody's dashboard.

## sendEmail discards the only outcome anyone needs to record

`[VERIFIED]` `lib/notify.ts:4` — `export async function sendEmail(payload: { to: string; subject: string }): Promise<void> {`. The signature makes distribution outcome unrecordable by construction: no caller can branch on it, persist it, or retry it. Spec §1 states the server *"generates a report that is distributed to insurers"* — for that business event, "did it arrive" is the fact anyone would be asked about, and this function is built so the answer cannot exist.

The log lines cannot substitute, because they carry no identifier to act on. `[VERIFIED]` `lib/notify.ts:19` — `console.error("[notify] send failed", e);` — no report id, no tenant id, no recipient. `[VERIFIED]` `lib/notify.ts:17` logs only `res.status`. Concrete scenario: three insurers do not receive reports on Tuesday; you can see three `[notify] non-2xx` lines and you cannot determine which reports, which tenants, or which insurers, so you cannot resend and cannot answer the customer. This is the failure mode where a rising count on a dashboard is useless because no single instance is reproducible.

Prescribed: return `{ok: true, providerId} | {ok: false, reason, status?}`; include `reportId` and `tenantId` in every emit at warn or above; persist a per-report distribution record so "which reports have not been distributed" is a query rather than a log search. Note the file header comment `[VERIFIED]` `lib/notify.ts:2` — `* Fire-and-forget: reports errors loudly but never throws, so callers do not fail.` — documents this as intentional. Not-throwing is defensible; *not returning* is the part that removes the signal, and the comment shows the two were treated as one decision. `[INFERENCE]` on the prescription.

`eng-contract` may also answer `interface_contract` for this signature; I am claiming it for the detection consequence specifically and defer to their reading of the broader export surface.
