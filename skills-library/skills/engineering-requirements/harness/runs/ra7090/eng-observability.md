by: eng-observability
contributed: [eng-observability]
categories:
  observability:  {state: PRESCRIBED, ref: "#the-alerting-fleet-terminates-in-one-unverified-email", by: eng-observability, blocking: true}
  failure_modes:  {state: PRESCRIBED, ref: "#field-evidence-is-dropped-on-the-device-and-the-server-never-learns", by: eng-observability, blocking: true}
  test_oracle:    {state: PRESCRIBED, ref: "#nothing-in-the-v1-exit-gate-ever-proves-an-alert-fires", by: eng-observability}
cross_domain:
  - "capture-manifest collapses a malformed/rotated device public key into SIGNATURE_INVALID, so a key-storage defect is reported to the caller as evidence tampering — eng-secrets owns whether that conflation is correct at the security boundary"
  - "CRON_ALERT_EMAIL and RESEND_API_KEY are both absent-means-silent-no-op in production with no startup assertion — eng-secrets owns config presence validation"
  - "the offline queue drops a stale-409 payload rather than reconciling it; whether that is the right merge rule at all is eng-concurrency's call, not mine — I only claim nobody can see it happen"

## The alerting fleet terminates in one unverified email

Credit first: this repo is well above the median. `lib/cron/expected-jobs.ts` is a real deadman registry with per-job staleness budgets, and `app/api/cron/cron-watchdog/route.ts` is the heartbeat check my seat usually has to invent from scratch. Three specific holes remain, and all three fail in the same direction — the system reports itself healthy while nobody is being told.

**1. The watchdog records that it alerted when it did not.** `app/api/cron/cron-watchdog/route.ts:72-77` [VERIFIED]:

```
        await sendEmail({ ... });
        alerted = true;
```

`sendEmail` cannot fail — `lib/email-send.ts:3` [VERIFIED]: `" * Fire-and-forget: reports errors loudly but never throws, so callers"`, and its signature is `Promise<void>` (`lib/email-send.ts:23`), with both the missing-config path (`:26-37`) and the non-2xx Resend path (`:62-71`) returning normally. So when Resend 401s on a rotated key, the watchdog run is written to `CronJobRun` as `status: "completed"` with `metadata.alerted: true`. The audit table then asserts the operator was notified on exactly the nights they were not. This is success declared before the effect is durable, and the durable record is the one an investigator will trust six months later.

**Prescribe:** `sendEmail` returns a delivery outcome (`{sent: boolean, reason?}`) — it may still not throw — and the watchdog sets `alerted` from that, records `alertDeliveryFailed` in metadata, and fails the run when a problem was detected and the notification did not leave the building. The rule (METHOD §6) is a lint or a type: no `void`-returning notify function on an alert path.

**2. Nothing detects the watchdog's own absence.** `lib/cron/expected-jobs.ts:76-77` [VERIFIED]: `" * - cron-watchdog: it cannot alert on its own failure (it is the alerter); a"` / `" *   watchdog crash still surfaces as an HTTP 500 to Vercel Cron."` That reasoning holds only if a 500 from Vercel Cron reaches a human. `docs/compliance/OBSERVABILITY-SETUP.md:31` [VERIFIED]: `"**Set up an alert policy**: Project → Observability → Alerts → \"new error spike\" → route to email or Slack webhook. Recommended threshold: 10 errors/min for 5 min."` — a once-daily cron producing one 500/day never reaches 10/min, ever. And that policy is under the heading at `:26`: `"## What the user still needs to do (≈ 5 min in Vercel dashboard)"` — it is a manual dashboard click with no artefact in the repo, so no review, deploy or test can observe whether it exists. Concretely: the Vercel cron entry for `cron-watchdog` is removed in a `vercel.json` edit, or the plan's cron quota is exceeded, or the route 500s on a Prisma change. Detection for all nineteen monitored jobs stops. Time until anyone knows: unbounded — the 2026-07-06→07-09 Ascora incident the watchdog was built for repeats one level up.

**Prescribe:** an external heartbeat the deployment does not own — the watchdog pushes to a hosted dead-man URL (healthchecks.io/Better Stack, ~$0) on each successful run, and *that* service pages on absence at 26h. This is the boring version (METHOD §1): the sophisticated version is self-monitoring, and self-monitoring cannot observe its own non-execution.

**3. Three storage crons emit no health signal at all.** `lib/cron/expected-jobs.ts:73-75` [VERIFIED]: `" *   their work in runCronJob, so they emit no CronJobRun rows to inspect."` / `" *   TODO(RA-7026): wrap these in runCronJob, then promote into MONITORED_CRONS."` These are `storage-mirror`, `storage-mirror-recovery`, `storage-restore` — the jobs that move claim evidence between buckets. Under §30 the evidence store is private-with-signed-URLs; if the mirror stops, the divergence is discovered at dispute-pack export, years later. Wrap them before V1, not after.

**Also prescribe, spec-level:** §37 currently says (spec.md:294) `"alerts edge-triggered on state change"`. An edge-triggered model is structurally incapable of detecting absence — no invocation, no state change, no edge, no alert. §37 must additionally require *level*/staleness checks: a named deadman per scheduled job and per external ingest (Stripe webhook, Ascora inbound, Xero sync), each with a stated budget and a named recipient. I am contradicting nobody here; I am naming that the spec's one observability sentence describes only the half of alerting that cannot catch the failure this product actually had.

## Field evidence is dropped on the device and the server never learns

Scenario, exact: a technician captures 40 moisture readings in a basement with no signal. Back in range the queue drains. `lib/nir-sync-queue.ts:503-514` [VERIFIED]:

```
        // us this queued payload predates the latest server state for
        // this resource. Drop the entry silently; storing a conflict
```
followed by `if (serverPayload?.stale === true) { await removeEntry(db, entry.id); }`. Separately, at `:472-474` [VERIFIED]: `"if (entry.retryCount >= getMaxRetryCount(entry.type)) { await markEntryFailed(db, entry.id); continue; }"` — a permanently-failed entry is parked in IndexedDB with `status: "failed"`.

Both outcomes are device-local. I grepped `lib/nir-sync-queue.ts` and `lib/evidence-upload-queue.ts` for `reportClientError`, `/api/observability`, or any server POST other than `entry.endpoint`: zero matches [VERIFIED — `grep -n "reportClientError\|/api/observability\|fetch(\"/api" lib/nir-sync-queue.ts lib/evidence-upload-queue.ts` returned nothing]. So no manager, no ops dashboard, and critically no completeness projection (§25) ever sees that 40 readings exist and did not arrive. The completeness engine evaluates what landed; a reading that never persisted cannot register as missing. §20's acceptance criterion — `"a report generated from a claim contains every moisture reading captured in the field for that claim"` (spec.md:202) — passes vacuously, because "captured in the field" is measured server-side. The damage travels all the way to a report delivered to an insurer under §23's closure gate, and surfaces at dispute, which is the one place this product cannot afford to be surprised.

Two aggravating specifics: the technician has to open a queue UI to see the `failed` count, and the `stale: true` drop is invisible even there. And if the device is wiped, reimaged, or the tech leaves, the evidence is gone with no record it ever existed.

**Prescribe:** (a) every terminal queue outcome — `markEntryFailed` and the stale-409 drop — POSTs a small durable receipt to a server endpoint (`inspectionId`, entry `type`, `queuedAt`, reason, count), best-effort but retried on the next drain, so the record survives the device; (b) an org-scoped counter of unreconciled field mutations per claim, surfaced on the claim and included in the §25 completeness output as an advisory finding; (c) closure (§23) reads that counter and refuses a clean close while it is non-zero for the claim, or requires an explicit acknowledged-loss reason. (c) is the part that turns a metric into a control; without it the counter is a dashboard nobody opens.

## Nothing in the V1 exit gate ever proves an alert fires

spec.md:298 [VERIFIED] enumerates exactly what every acceptance criterion must state:

> Each criterion states: starting state, user role, user action, expected system behaviour, expected data write, expected audit event, expected failure behaviour, expected concurrency behaviour, expected offline behaviour where relevant.

There is no **expected detection signal**. An audit event is a record written for later reading; it is not a signal that reaches a human at the time. Consequently the §39 seeded reference claim — the V1 exit gate — is a happy-path traversal, and §42's definition of done can be fully satisfied by a system in which every alert path is dead. The `[error]` structured sink is real (`lib/observability.ts:32`) but only 8 of 515 `app/api` route files reference `reportError` [VERIFIED — `grep -rl "reportError" app/api | wc -l` → 8; `find app/api -name route.ts | wc -l` → 515], so any policy filtering on that shape covers a rounding error of the surface. This is METHOD §10 applied to monitoring: the question is not whether alerting was written well, it is what proves it correct and whether that thing has ever failed on purpose.

**Prescribe** two things, both cheap:

1. Add `expected detection signal` to the §38 criterion template: for each capability, which alert fires, with what identifier in it (claim id / org id / job name — my seat's recurring finding is the alert that says "sync failed" and cannot be traced to one claim), and within what budget.
2. Add one negative step to the §39 reference claim: with the seeded claim mid-drying, disable the `sync-xero-payments` cron (or point `CRON_ALERT_EMAIL` at a mailbox under test and fail one job deliberately), and require the run to record *receipt* of the alert as evidence. This is the positive control — a watchdog that has never once alerted in anger is an untested watchdog, and a `0 problems` report from a broken query looks identical to a healthy fleet.

Note where the method overruled my instinct: I would normally also ask for per-org SLO dashboards and log sampling policy. METHOD §13 says three actionable findings beat ten hedged ones, so those are out — at this stage they would cost more attention than they return.
