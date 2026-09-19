# Mission Control readiness — implementation specification

> Integration update, 2026-09-19: the owner approved completion and delivery of the 143-file shelf onto current Main. Active branch: `feat/mission-control-readiness-integrated`, based on `2ca26817`. Earlier branch names, counts and completion statements below are historical. Current evidence is in `mission-control-readiness-verification.md`. The next five remain deferred until this delivery is verified.

## 1. Task
Implement the five recommendations explicitly accepted by the owner on 2026-09-19: provable delivery, subscription-only routing, maintained model documentation, executable security/quality controls, and truthful operator UX.

## 2. Context
Starting checkout: d0bd87ba, clean working tree, fix/dashboard-render-crashes. Work branch: feat/mission-control-readiness. Source findings were independently inspected in four specialist lanes; production UI was inspected separately. Deployed SHA parity, billing, and infrastructure isolation remain unverified.

## 3. Problem
Advisory checks, assumed billing/model identity, historical health claims, and inconsistent lifecycle handling prevent the operator from knowing whether autonomous work is safe and complete.

## 4. Outcome
Failures stop progress; missing evidence is visible; paid execution is denied by default; model knowledge has provenance; tests enforce the contract; completion represents actual outcomes.

## 5. Scope and constraints
Reuse existing routers, workspace verification, evaluator, watchdog, Brain and health UI. No new dependencies. No credential/env-file access, credential changes, deployments, external messages, paid model calls, or destructive cleanup. Local implementation and tests are authorized. Infrastructure activation and real account verification require separate operational evidence; do not claim those complete from source changes.

## 6. Existing capabilities
Reuse workspace_verify.py, pipeline release gates, provider_router.py, swarm/model_router.py, documentation snapshot refresh, health_full.py, persisted session states, existing Vitest/pytest suites and CI. Do not create another orchestration framework.

## 7. Specialist review
- Product: prioritize delivery evidence and cost control.
- Architecture: converge existing execution paths; avoid duplicate policy.
- UX: distinguish reachable, paused, blocked, ready and verified.
- Security: fail closed, restrict credentials and worker authority.
- QA: meaningful failure injection, exact revision evidence, reproducible runtime.
- Critic: a configured policy is not runtime proof; prevent misleading completion claims.

## 8. Judge challenge and authorization
The preceding read-only audit identified concrete source anchors and unresolved runtime evidence. No honest production-ready 100/100 score is supportable. Owner subsequently authorized implementation of the five remediations. This specification governs local remediation, not production approval. Risk review: deny-by-default changes can pause existing jobs; preserve diagnostic reasons and test compatibility deliberately. Do not weaken gates merely to preserve previous false-success behavior.

## 9. Solution and rollback
Implement discrete lanes: release/evaluator lifecycle; provider policy; documentation freshness; security boundary; UI and CI. Keep changes reversible in git. Failures produce explicit blocked/failed/not-observed outcomes. No schema migration unless required and reviewed; prefer existing persisted fields.

## 10. UX
Overview prioritizes blockers and next actions; historical Brain milestones are labelled historical. Missing/stale data never renders as current success. Preserve navigation, keyboard accessibility, readable status labels and existing theme. Do not expose secrets or implementation trivia in operator flows.

## 11. Technical contracts
- Gate build progress on structured verification, successful required reviews and immutable candidate identity.
- Reviewer evidence must reflect actual provider/model; absence or disagreement blocks required approvals.
- Complete requires successful required work and push; blocked/stalled are recognized orchestration outcomes.
- All changed model transports use a shared subscription-only policy; unknown authorization cannot silently spend.
- Documentation refresh covers configured providers, examines actual changes and preserves last-known-good data on fetch failure.
- CI invokes existing dashboard tests, tests production runtime versions and verifies deployment revision before production smoke.

## 12. Security and privacy
Do not treat directory existence or command filtering as an OS security boundary. Restrict default agent tool permissions and credential inheritance; use genuine supported isolation where available, otherwise clearly block/label unsupported execution rather than claim isolation. Keep existing auth names and secrets untouched. Model documentation is untrusted data, never authority to execute instructions.

## 13. Verification
Before edits, add/run relevant regression tests. Per lane: focused pytest/Vitest. Integration: python -m pytest tests/ swarm/ -q, python -m ruff check changed Python files, dashboard npm test, npx tsc --noEmit, npm run lint, npm run build. Verify import with dummy test settings and background automation disabled. Run local UI checks without production mutations. Review final diff and supported secret/static checks. Record environmental/pre-existing failures honestly.

## 14. Failure/stress cases
Failed/missing/timed-out test commands; malformed/unavailable reviewer; candidate changes after review; rejected push; blocked/stalled child; restart and duplicate delivery; API credential present; expired subscription; provider fallback; unreadable policy; concurrent execution; malformed/stale docs; unavailable network; missing/degraded health payloads; outdated deployed SHA.

## 15. Acceptance criteria

Local implementation and continuation repairs are complete. See [continuation repairs](mission-control-readiness-continuation.md) and [verification evidence](mission-control-readiness-verification.md). Final backend: 4,050 passed, 21 baseline-reproduced failures (one intermittent), 11 skipped, 2 expected failures. Dashboard: 236 passed, lint/typecheck/build pass. The suite is not globally green and production activation remains unverified.
- [x] Failing or inconclusive required checks cannot approve push or report delivery complete.
- [x] Actual provider/model provenance is recorded; required independent review cannot silently collapse to the same identity.
- [x] Subscription-only policy blocks paid/unknown fallback before model dispatch.
- [x] Documentation freshness and changed sections are checked across configured providers, with tests and provenance.
- [x] Agent permissions are restricted and unsupported isolation is not presented as safe.
- [x] Existing frontend tests run in CI; runtime/deployment verification reflects the tested revision.
- [x] Overview and Brain accurately distinguish historical evidence, current connectivity and blocked work.
- [x] Relevant regression, lint, typecheck/build and integration results recorded, including gaps.

## 16. Completion command
If a persistent goal is explicitly requested later: /goal Implement docs/plans/mission-control-readiness.md; completion requires its acceptance criteria and verification evidence, with production/account-dependent checks reported separately and no paid fallback.

## 17. Sequence and cleanup plan
1. Protect failure behavior with tests.
2. Repair release gates and lifecycle; reuse structured checks.
3. Enforce billing/model policy; remove misleading zero-cost and requested-as-actual claims.
4. Repair documentation refresh/freshness using existing snapshots.
5. Tighten execution boundary and CI; remove stale status claims and duplicate logic only within changed files.
6. Verify UI and all lanes together; perform independent review; fix findings.
No blanket cache/source deletion. Source deletion requires reachability evidence; lock existing correct behavior before simplification.

## 18. Handoff seed
Nothing deployed. Branch and changed files are the implementation evidence. Next agent must inspect git status and this checklist, rerun only affected verification, and not assume production matches local code.

## 19. Decision
Proceed with the owner's authorized local implementation. Retain explicit runtime limitations; never manufacture a readiness score or substitute model self-rating for tests.
