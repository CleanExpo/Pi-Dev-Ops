# Mission Control readiness: integration verification

Date: 2026-09-19. Branch: `feat/mission-control-readiness-integrated`.
Base: `2ca2681719b4e475e33f6a09e67c6d0ab1bf1144`.

## Scope and reconciliation

Complete the owner's 143-file shelf against current Main while preserving newer upstream behavior. The original shelf and verified recovery bundle remain in `D:/Pi-Dev-Ops`; its old verification report is historical, not merge evidence.

All 143 original paths are accounted:138 integrated,4 already delivered by PR #783,1 superseded by Main's checkpoint helper. See `mission-control-readiness-files.json`. Supporting extractions preserve Main's unchanged 300-line file and 40-line function ratchets. Existing auth, planner, leases/recovery, routing observations, Control and LiveWall behavior is retained.

## Local evidence

Counts below overlap and must not be summed.

| Scope | Observed result |
| --- | --- |
| Dashboard | 503 tests passed; production build, TypeScript, lint passed; two unchanged lint warnings |
| Parent health/autonomy/test isolation/spec delivery | 64 tests passed; subsequent 53 reporter/delivery tests passed |
| Provider/policy and Main routing compatibility | 362 tests passed |
| SDK/tool/Git integration | 336 passed, 7 Linux-only skips |
| Delivery/lifecycle | 287 passed; subsequent 75 related, 35 compatibility, 5 new lifecycle regressions passed |
| Main candidate fixtures | 13 tests passed across 3 files |
| Required GitHub CI evidence | 108 passed, 1 Linux-only skip |
| Documentation/runtime | 73 tests passed;97 Linux CPython 3.12 distributions downloaded and hash-validated |
| Static gates | Ruff and compilation of all changed Python files passed; file/function ratchets, proxy, gate parity, baseline integrity and diff checks passed |
| Secret scan | Dry-run scanner passed with exclusion preconditions; no external alerts or credential changes |

Independent review closed concrete blockers in required-check identity/pagination, all-seven-phase output schemas, recovered/manual task ownership, failed child cancellation, and guarded recovery cloning. All reviewed slices now have PASS verdicts.

A real WSL probe verified deterministic workspace writes, host/network isolation, immutable Git metadata and cancellation cleanup. It does not prove live SDK/provider entitlement or deployed-container behavior.

## Full candidate verification

The complete isolated Linux suite passed: **6,551 passed, 20 skipped, two expected failures**, exit 0. It used Ubuntu WSL2, Python 3.12.3, hash-locked Python dependencies, existing locked Remotion dependencies, actual Main history, isolated HOME/tmp and no external network. The 2,921-file snapshot matched the candidate throughout the run; subsequent smoke-inventory changes were verified separately. Evidence manifest SHA256: `29a4ad0cc2b8d168633284b505ed049231360ab80745f7633718ba6a22be5414`.

Native Windows full collection remains unsuitable for Main's Linux-only fcntl modules. The Linux run supplies the full-suite evidence. Real verifier lifecycle checks separately passed all 37 cases without skips.

CI follow-ups register the revision/Overview/Builds smoke surfaces and reconcile exact golden routing expectations with the approved subscription defaults. Surface checks passed 37 Python and 29 dashboard tests; golden evaluations passed 129 tests with one skip under the CI environment. No assertions, size baselines, auth expectations or paid-transport prohibitions were weakened.

[PR #784](https://github.com/CleanExpo/Pi-Dev-Ops/pull/784) carries the final commit checks and authoritative delivery state. Exact-candidate CI must pass before merge. Local verification does not establish production readiness.

## Post-merge continuation

PR #784 merged as `bb23e877`. Its fourteen always-triggered PR quality checks and conditional smoke-surface gate passed. The original 143-file shelf was archived and retired, with a durable local `refs/backups/readiness-delivered-pr784` recovery ref. A subsequent wiki-only Main commit, `9e4df735`, superseded the merge's deployment: GitHub reported both Railway and Vercel successful for that successor, while the merge's Railway deployment was cancelled. These deployment statuses do not prove runtime execution readiness.

Late review found that unexpected orchestration exceptions, including a kill-switch abort, could leave owned child builds running. The continuation reuses the existing cancellation helper on both cancellation and ordinary exceptions, preserves the original error plus worker-stop failures, and tests that workers cannot deliver after the parent fails.

Production smoke also requested protected backend revision details without authentication. The continuation uses the existing authenticated health contract, limits the credential to the original request (not redirects), and keeps missing/wrong authentication or revision blocking before any smoke actions. Public health and exact forty-character SHA checks are unchanged. Backend admission now shares the existing smoke-admission module, reducing the oversized entry script below its prior baseline.

The combined continuation passed **6,561 tests, 20 skipped, two expected failures** in the isolated Linux environment, plus **129 golden evaluations, one skipped**. The safe FastAPI import passed with 142 routes and no application startup. The 2,923-file snapshot had no source drift; manifest SHA256: `ac5fc43e903435e4e989197e82b3004e0eae9d052d40c0aa47512afdec8a7a93`. This snapshot precedes this evidence-only documentation update. Focused regressions failed before the fixes and passed after them. Independent review passed both fixes (bounded source evaluator 9/10); Ruff, file/function limits, proxy checks, gate parity, whitespace and dry-run secrets scan passed. No size baseline or gate was weakened.

The production E2E check already authenticates through the dashboard. Its original exact-SHA run failed while deployments advanced to the wiki successor; this continuation does not substitute a newer SHA or relax admission to make that historical run green. Live account, billing and supported-host execution remain unverified.

## Activation limits

No live provider workload, credential change or billing verification has been performed. Automatic deployment statuses are recorded above; they do not establish execution readiness. Native Windows generation remains explicitly unsupported by the isolation boundary. Docker's extra bubblewrap/socat activation packages await explicit dependency approval; the original Docker/lock changes are integrated and generation fails closed without prerequisites. Independent review requires a configured distinct verified vendor/model. Unknown authorization, model identity, cost or delivery proof remains blocked/unknown.

Main's existing protection is readable but has no required status-check policy. A narrow, independently reviewed proposal requires the fourteen always-triggered quality jobs, bound to GitHub Actions app 15368, with branches up to date. The path-filtered surface gate and post-merge production check cannot be unconditional PR prerequisites. This policy is prepared locally, not applied; other branch settings, including the current administrator bypass setting, remain unchanged.
