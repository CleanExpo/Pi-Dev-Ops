# SPM spec — restore Pi-CEO responsiveness during Linear quota failure

## 1. Task
Repair the production autonomy poll so a Linear rate limit does not make Mission Control and `/health` time out.

## 2. Current context
Clean `origin/main` at `aeab1d2f` on `fix/autonomy-linear-rate-limit-20260929`. Railway production was observed RUNNING at `827b12b7` during the incident. On 29 Sept, Railway HTTP logs show repeated 499 responses for `/health`, `/api/projects/health`, and `/api/mission-control/live`; deploy logs show Linear `RATELIMITED` on successive portfolio project and label queries. The MacBook browser reports the backend unreachable. `app/server/autonomy.py` calls synchronous `urllib.request.urlopen` from `_run_poller_iteration` on the event loop; `fetch_todo_issues` continues after every error. Existing tests cover a single project's failure but not quota exhaustion or event loop liveness.

## 3. Problem
The operator loses the cockpit during a background queue poll. Linear quota errors are repeated for every remaining project and label, worsening the outage and masking useful failure evidence.

## 4. Desired outcome
The API event loop continues serving requests while a Linear read is slow; a quota response stops that scan promptly without claiming a partial queue. A bounded shared cooldown and five-minute queue/one-minute pulse caches prevent five-second live-view polls from hammering Linear during and after the exhausted hour.

## 5. Scope
In: classify Linear `RATELIMITED`/HTTP 429 responses, abort the current portfolio scan, offload the poller's blocking scan and startup recovery, isolate and cache the live route's blocking Linear reads, share a cooldown, and add targeted tests. Out: changing poll interval, credentials, provider budget, dashboard, deployment, or auto-ship authority. Assumption: the observed 499s correlate with event-loop blockage; validate with a regression that ticks the loop while mocked reads block. Other synchronous work in the issue-processing path is a separate follow-up if healthy-queue latency fails.

## 6. Existing capability
Reuse `fetch_todo_issues`, `_gql`, `_run_poller_iteration`, the existing 300-second poll schedule, existing `poll_error` event, and the Mission Control deterministic read suite. JEV is advisory after deterministic checks, not a pass/fail or release authority.

## 7. Specialist board
Product: preserve an available cockpit. Architecture: isolate the poller and five-second live route's blocking I/O without rewriting ownership. UX: existing unreachable state is honest while restoration is checked; queue counts during quota remain unknown to the backend but the existing response shape cannot express this yet. Security: no key or response body in new quota logs. QA: test HTTP 429, structured GraphQL RATELIMITED, first-call stop, partial queue discard, startup recovery and event-loop liveness. Judge: avoid retry bursts and partial queue processing. The cold engineering bench found the original poller-only scope insufficient and expanded this spec before implementation.

## 8. Judge challenge
Evidence 25/25, problem 20/20, reuse 15/15, security 15/15, UX 10/10, testability 10/10, cost/control 5/5 = 100/100 for this revised bounded candidate. Decision: proceed to a candidate only; independent review and production proof remain separate. The 499 causal link remains an inference until the liveness regression and post-release observation.

## 9. Solution
Raise a specific sanitized quota exception from HTTP 429 and GraphQL `RATELIMITED`. Propagate it through `fetch_todo_issues` to the existing poll-error boundary, returning no partial issues. Register a process-local monotonic cooldown of one hour after quota rejection; the poller retains its schedule but skips external Linear reads until cooldown expires. Run synchronous queue fetch and orphan recovery off the event loop. Offload the live route's queue and pulse reads; cache successful queue results for five minutes and pulse results for one minute under one process-local lock per source, and honour the same cooldown. Cache never stores an error fallback, and logs never include vendor response bodies. No cancellation claim: a running thread still finishes its bounded request. Roll back by reverting the branch change.

## 10. UX
No new controls. A healthy backend restores real project status; if upstream data is absent, existing Unknown/unreachable states remain honest.

## 11. Technical
Modify `app/server/autonomy.py`, its small quota-state helper, `app/server/routes/mission_control.py`, and relevant tests. No schema, env, public API, credentials, or payload changes. Keep `/health` autonomy status semantics. `_last_poll_at` is a start tick, not a successful-poll metric; verify `poll_error` for failure truth.

## 12. Security and privacy
Keep API keys out of exceptions and receipts. No real customer data leaves the repo. JEV uses synthetic snapshots only in the current runner. No production mutation in this candidate.

## 13. Verification
Run targeted autonomy and live-route tests, 1,000 varied offline quota/liveness cases, `python -m pytest tests/ -x -q`, and `python -c "from app.server.main import app; print(type(app))"`. Run the existing JEV synthetic shadow tests and offline receipt. Review diff and exact SHA; after human-controlled release, inspect Railway HTTP `/health`, `/api/projects/health`, and `/api/mission-control/live` latency across two poll intervals, plus one sanitized `poll_error` and no repeated Linear calls during quota.

## 14. Stress cases
Normal result, empty result, one project failure, first quota failure, quota after a partial result, HTTP 429, structured GraphQL quota body, malformed response, repeated quota failures, startup recovery, five-second live route, and a slow blocking fetch while the event loop stays responsive.

## 15. Acceptance
- [ ] Quota halts the current scan with no partial claims.
- [ ] An event-loop ticker runs during blocked poller, startup recovery, and live route Linear reads.
- [ ] Repeated live views make no further Linear calls while quota cooldown is active and use bounded caches after it expires.
- [ ] Existing one-project failure recovery still works.
- [ ] Full required tests and import gate pass at the candidate SHA.
- [ ] JEV remains advisory and no live secret/data egress occurs.

## 16. Goal
`/goal Implement this accepted SPM spec. Completion: bounded quota stop and event-loop liveness proven by tests; full server gate and offline JEV receipt pass. Constraints: no unrelated edits, no production switch, human merge.`

## 17. Sequence
Write failing regressions; implement small repair; run focused, repeated, full and import gates; inspect diff; prepare review evidence. Investigate healthy issue-processing latency separately if route-level proof fails.

## 18. Handoff seed
Branch `fix/autonomy-linear-rate-limit-20260929`; base `aeab1d2f`; production incident 29 Sept; check `app/server/autonomy.py`, targeted tests, Railway read-only logs, and this spec.

## 19. Recommendation
Proceed with candidate implementation. Release remains gated on independent review and human merge.
