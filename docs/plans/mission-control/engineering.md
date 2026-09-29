---
type: engineering-requirements
spec: ./autonomy-linear-rate-limit-spec.md
spec_sha256: c50e99db9c93a61f3d7851053096bb2559a68d37da59001facf63a41e7bffdc1
reviewer: bench
seated: [boris, eng-failure, eng-observability, eng-test, eng-release]
reviewed_at: 2026-09-29T15:27:00+10:00
status: PASS
categories:
  data_model: {state: N/A, reason: "No persistent schema changes; revisit if a new rate-limit table or migration is proposed.", by: boris}
  invariants: {state: DECIDED, ref: "#invariants", by: boris}
  failure_modes: {state: PRESCRIBED, ref: "#failure-modes", by: eng-failure}
  interface_contract: {state: DECIDED, ref: "#interface-contract", by: boris}
  concurrency: {state: PRESCRIBED, ref: "#concurrency", by: boris}
  migration: {state: N/A, reason: "No database or disk format changes in this diff; revisit before any migration file is added.", by: eng-release}
  rollback: {state: DECIDED, ref: "#rollback", by: eng-release}
  observability: {state: PRESCRIBED, ref: "#observability", by: eng-observability}
  budget: {state: N/A, reason: "No metered HTTP request path or TYPESAFE_API_KEY access is added; revisit if jev_triage.py --live is wired.", by: eng-release}
  test_oracle: {state: PRESCRIBED, ref: "#test-oracle", by: eng-test}
disagreements:
  - "Initial SPM scope offloaded only the poller's queue fetch; the bench found startup recovery and the five-second live route also block. The chair expanded scope before implementation."
---

## Invariants
> The API event loop continues serving requests while a Linear read is slow; a quota response stops that scan promptly without claiming a partial queue.

Normal per-project nonquota failure remains recoverable. Quota returns no partial candidates for session creation.

## Failure modes
Structured GraphQL `extensions.code == RATELIMITED` can arrive as HTTP 400. HTTP 429 can carry an arbitrary body. Match only the structured code or status, sanitize the outward error, and stop the scan. A rate limit after earlier valid candidates must discard them. Other errors retain the existing continue behavior. The process-local cooldown cannot coordinate multiple replicas; if replicas are added, revisit shared quota state.

## Interface contract
> No schema, env, public API, credentials, or payload changes.

Keep the existing `/live` queue and pulse keys and `/health` autonomy boolean. A later product change may need an explicit unknown queue state, but it is outside this repair.

## Concurrency
Use a thread for synchronous portfolio reads, startup recovery, and live-route reads. Startup orphan recovery attaches the session-lost reason label before changing state. A quota response during label attachment leaves the ticket In Progress; the prior nonquota label-failure contract still transitions and comments with an attach-failed note. It pages through target-state tickets only to finish ones carrying that recovery label or an existing recovery comment, so a manually placed Todo/Blocked ticket with an old session comment is untouched; it follows comment cursors for session markers and recovery comments before posting. Quota at any mutation records a sanitized per-issue error and retries after cooldown without repeating completed mutations; a verified completion reconciles against the append-only recovery event log after process restart and emits a missing success event once per retained attempt. Each new transition logs an attempt before mutation, so an older success for the same ticket cannot mask a later recovery. If that local log is lost with the container, a completed target is recorded again with no Linear mutation. Preserve the existing single poller interval. An `asyncio.to_thread` cancellation does not interrupt its 15-second `urlopen`; the operation must remain bounded and avoid partial side effects for queue scans. The live route's five-second poll must consult the shared cooldown before I/O and reuse the five-minute queue and one-minute pulse caches. Serialize same-source refreshes so simultaneous viewers do not duplicate the portfolio scan.

## Rollback
> Roll back by reverting the branch change.

No migration is introduced. After human-controlled release, rollback also requires an authorised Railway redeploy of the previous code; no hidden automatic rollback is claimed.

## Observability
`_last_poll_at` is a start tick, not success. Record one sanitized quota `poll_error` in the existing event surface; do not store vendor response bodies or keys. Verify the deployed SHA and route latency across at least two poll intervals. A healthy `/health` alone does not prove queue pickup.

## Test oracle
Use a deterministic mocked HTTP 429, structured GraphQL RATELIMITED, partial candidate, and nonquota 500. Prove event-loop liveness with a bounded blocking worker and a ticker before release. Run 1,000 varied offline cases with fixed seed and no network; keep JEV receipts advisory. Run the full required server suite and import check before commit.
