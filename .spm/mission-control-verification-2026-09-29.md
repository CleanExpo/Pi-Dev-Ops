# SPM Spec — Mission Control verification and portable test gate

## 1. Task being planned
Verify the committed Mission Control visual slice at `77d59ac` and repair the smallest test harness obstacle that prevents the full backend suite from completing in this environment.

## 2. Current project context
Repo: `CleanExpo/Pi-Dev-Ops`. Branch: `feat/mission-control-portfolio-surface-20260929`. Tree was clean before this verification task. Relevant sources: `dashboard/components/control/PortfolioFocus.tsx`, `IdeaPipelinePanel.tsx`, `dashboard/lib/control/project-pathway.ts`, `app/server/pipeline.py`, the related tests, `scripts/route-exercise.mjs`, `scripts/handoff-loop.sh`, `AGENTS.md`, `CLAUDE.md`, and the prior visual plan in `docs/plans/mission-control-visual-overhaul-2026-09-29.md`. `/judge`, `/spm`, and `/session-handoff` exist in `.agents/skills/`. Unknown: live deployment and machine fleet status; sample browser responses cannot prove either.

## 3. Problem statement
Phill needs proof that the new page works before receiving it. The prior handoff lacked backend test evidence because Python dependencies were unavailable. An isolated environment now runs the backend, but the full suite encounters `EPERM` when a separate Remotion test starts `npx tsx`, whose CLI opens a Unix socket. This prevents an honest full-suite green result.

## 4. Desired outcome
Document exact test results at a commit, make the existing Remotion dry-run assertion portable without changing product behavior, and report any remaining limits explicitly.

## 5. Scope
In scope: provision an isolated Python test environment; run backend, dashboard, route, and browser checks; change only the Remotion test invocation if direct Node execution proves equivalent. Out of scope: production deploy, merge, fleet connection, approval automation, new Mission Control features. Explicit non-goals: infer live status from sample data or bypass failing assertions. Assumptions: `node --import tsx` executes the same `render/one-shot.ts` entry point. Constraints: no secrets in git, no production mutation, preserve the packet assertions.

## 6. Existing capability review
| Capability | Location/source | Reusable? | Notes |
|---|---|---:|---|
| Backend tests | `tests/`, `app/requirements.txt` | Yes | Isolated venv installed; targeted 34 pass. |
| Dashboard tests/build | `dashboard/package.json` | Yes | 510 tests, lint and build pass. |
| Route exercise | `scripts/route-exercise.mjs` | Yes | 18 internal paths pass with an environment-only network-interface shim. |
| Browser validation | Playwright in dashboard | Yes | Sample-backed mobile form error/retry passes. |
| Remotion dry run | `remotion-studio/render/one-shot.ts` | Yes | Direct Node import runs and writes a packet; `npx tsx` socket bind fails here. |

## 7. Specialist board review
| Role | Finding | Risk | Recommendation |
|---|---|---|---|
| Product | Phill needs visible, reviewable proof. | Sample data could be mistaken for production. | Label preview data. |
| Architect | Test invokes the same entry point through a CLI wrapper. | A rewritten assertion could weaken proof. | Change only invocation, keep assertions. |
| UX | Form validation and retry are central. | Losing a draft on failure. | Verify in browser. |
| Security | Test inputs and credentials are synthetic. | Secret leakage in logs. | Use local placeholders and avoid committing env files. |
| QA | Full suite blocked by Unix socket permission. | False green if skipped silently. | Re-run full suite after targeted repair. |
| Judge | Product release still lacks live evidence. | Overclaiming readiness. | Keep experiment separate from release approval. |

## 8. Judge challenge
For the **test harness repair only**: evidence 25/25 (observed CLI failure and direct success); problem 20/20; reuse 15/15; security 15/15; UX 10/10 (no product flow altered); testability 10/10; cost 5/5. Score 100/100, APPROVE BUILD for the narrow test invocation. This does not rescore or authorise release of the broader Mission Control slice, whose previous score was 86/100.

## 9. Proposed solution
User flow and system flow stay unchanged. The Python test invokes `node --import tsx render/one-shot.ts` with the existing synthetic brief and checks the same generated packet. Permissions and data flow stay local. On failure, pytest remains red. Rollback is reverting the one test command.

## 10. UX requirements
The `/control` entry point retains its current loading, empty, unavailable, and keyboard states. The idea composer retains short-text validation, draft on failed POST, retry, and confirmation on success. The test repair has no UI change.

## 11. Technical requirements
Likely changes: the two existing Remotion dry-run tests, `tests/test_remotion_one_shot_schema.py` and `tests/test_remotion_workspace_images.py`. No API, schema, auth, config, MCP, hook, or agent change. Keep the existing output assertions. The backend suite must run with the isolated Python environment first on `PATH` because a DoD probe starts `python3`.

## 12. Security and privacy requirements
No real credentials, customer data, external dispatch, or production writes. Protected dashboard routes stay protected. The synthetic idea POST is intercepted in browser QA. No prompt-to-tool execution is added. Publishing, merge, and deploy remain human gated.

## 13. Verification plan
Static: `git diff --check`; Python import with local test env. Integration: `python -m pytest tests/ -x -q` with venv on `PATH`. Dashboard: `npx tsc --noEmit`, `CI=1 npm test`, `npm run lint`, `npm run build` with build placeholders. Route exercise: `node scripts/route-exercise.mjs` with environment-only network shim. Browser: desktop/mobile sample render; idea validation, failed POST, retry, selected project and pathway. Full handoff loop may report environment skips or other repo gates; record exact verdict.

## 14. Loop testing and stress testing
Normal and retry: successful intake after a simulated 500. Empty/malformed: under-eight-character idea blocked. Large input: textarea limit remains 2,000 characters. Duplicate: two POSTs occur only after two intentional clicks. Permission failure and network failure: maintain unknown state or draft; no false completion. Regression: Remotion packet assertions remain unchanged. Human checkpoint: Phill reviews the branch before any activation.

## 15. Acceptance criteria
- [x] Both Remotion dry-run pytest cases pass without Unix socket permission (4 tests in their files).
- [x] Backend suite reports an exact result with seven nested-sandbox tests explicitly excluded: 6,459 passed, 18 skipped, 2 xfailed, 7 deselected. The unmodified full suite is **blocked** here by nested bubblewrap permissions.
- [x] Dashboard 510 tests, lint, typecheck, and production build pass.
- [x] Browser form validation, failure retention, retry, and route exercise pass with sample data.
- [x] Swarm suite: 345 passed, 2 skipped. Remaining release evidence limits are recorded below.

## 16. Goal command
`/goal Verify the accepted Mission Control visual slice and repair the portable Remotion test invocation. Completion condition: the full backend suite, dashboard tests/build, route exercise, and sample-backed browser checks finish with exact results; only the test harness changes if required. Required proof: command outputs, commit SHA, desktop/mobile previews, and a handoff. Constraints: no unrelated files changed, no secrets added, no destructive operations; stop and produce /session-handoff if blocked.`

## 17. Implementation sequence
1. Prove the existing tests fail and direct Node dry run succeeds (done). 2. Change the two test invocations only (done). 3. Re-run targeted and broad suites (done with the seven named exclusions). 4. Inspect diff, commit, handoff. The full repo gate remains blocked by nested sandbox tests and repo-wide Ruff findings; no release-ready verdict is asserted.

## 18. Session handoff seed
Branch and SHA; isolated venv path `/tmp/pi-dev-ops-test-venv` (ephemeral); commands and counts; environment-only Node network shim; browser preview uses sample responses; no push/merge/deploy; next owner to review real runtime evidence.

## 19. Final recommendation
Proceed with the narrow test harness repair and verification. Hold product release for a separate exact-SHA review and live evidence.

## Verification record
- Backend import succeeds with the isolated Python environment and synthetic test credentials.
- `tests/test_pipeline_routes.py`, `tests/test_idea_pipeline_route.py`, and `tests/test_idea_pipeline_board.py`: 34 passed.
- `tests/test_remotion_one_shot_schema.py` and `tests/test_remotion_workspace_images.py`: 4 passed after replacing `npx tsx` with `node --import tsx`; their output assertions are unchanged.
- Full `tests/` with only seven real nested-bubblewrap cases deselected: **6,459 passed, 18 skipped, 7 deselected, 2 xfailed**. The unmodified full suite stops on `tests/test_verification_sandbox.py::test_real_sandbox_can_work_but_cannot_reach_host_files_or_network` in this already-sandboxed runtime. Four `tests/test_workspace_verify.py` cases and two `tests/test_workspace_verify_lifecycle.py` cases also require real bubblewrap. Re-run all seven on a host that permits nested namespaces.
- `swarm/`: **345 passed, 2 skipped**. Dashboard: **510 passed**, lint 0 errors (2 existing warnings), `tsc` and production build pass. Route exercise: 7 pages and 18 internal paths pass with a local Node network-interface shim. Mobile browser: validation, failed POST retaining draft, retry, and zero page errors; sample responses only.
- Repo-wide `ruff check app` with newly installed Ruff 0.16.9 reports 1,233 findings; this predates the two test changes. Both touched tests pass Ruff. Full `handoff-loop.sh` therefore has no READY verdict in this environment.
- No live Mac Mini, PC, GitHub PR, or production deployment was exercised.

## Post-verification evidence correction
- The scanner returns `overall_health: 100` and `scores: {}` when there are no scan files. The portfolio card had displayed that sentinel as `100/100`. It now shows `Unknown` and `No scan evidence` until a finite scan score is present. A focused regression test covers the empty-score response.
- The idea composer now states that its Board inbox covers all projects and a selected card does not attach an idea to that project.
- At this revision, dashboard verification is **511 passed**, typecheck passed, lint exited 0 with the two existing warnings, and production build passed with local placeholder settings. Mobile browser QA with synthetic `overall_health: 100, scores: {}` showed Unknown, kept a draft after a simulated 500, succeeded on retry, and reported zero page errors. The earlier backend, swarm, and route results above were obtained before this UI-only correction; their environmental limits remain.

## Variation gate requested before the next commit
- Current Vercel connector identifies `Unite-Group/pi-dev-ops` as project `prj_I5sYqNTlL51DlvyzSFjiHX6FrLAX`, but its available project operation does not return environment variables. The repo's JEV contract states `TYPESAFE_API_KEY` was configured for that project on 28 September; its current presence and value were not verified. This workspace has no TypeSafe key and `api.typesafe.ai` timed out. No JEV call was made or credited as test evidence.
- The official TypeSafe skill describes a typed advisory judgment layer over code-owned workflows. The repository's WP-10 shadow evaluator is planned, not implemented; JEV must never decide pass/fail, merge, or deploy. A direct live test still requires an accessible runner, scoped key and redacted snapshots.
- Uncommitted variation checks: 1,000 distinct project scan states, 1,000 repository timeline matches and release stages, and 1,000 Board packets for GO eligibility. The existing render tests remain. The dashboard has **514 passed** across 57 files; typecheck, lint (two existing warnings), and production build pass.
- A synthetic local browser session switched among ten projects **1,000 times**, checking selection after each click: median 49 ms, p95 132 ms, max 286 ms, zero page errors. These are local browser interaction times and do not measure real fleet, network, deployment, or production transition latency.
- This gate was initially held uncommitted for review; Phill subsequently authorised the local build to proceed. The seven nested-bubblewrap backend cases and live JEV evaluator remain outstanding; no release or reconstruction completion is claimed.

## Local JEV shadow candidate
- Added `scripts/mission_control_jev_shadow.py`, `tests/test_mission_control_jev_shadow.py`, and `docs/plans/mission-control/jev-shadow-runner.md`. The script reads allowlisted JSONL browser snapshots and writes advisory labels tied to run ID, SHA and surface. Offline is the default and records `NOT_EVALUATED`; a live call requires `--live-synthetic`, a key and a persistent SQLite budget ledger. Real-data egress is rejected.
- Questions J1–J4 follow the repo's decision contracts. The request shape, answer schema and input usage were checked against the current official TypeSafe API reference. It never changes deterministic assertions or release status.
- Focused verification: **13 passed**, including 1,000 varied offline snapshots and 1,000 varied synthetic calls to a fake HTTP responder; no actual TypeSafe request was made. Ruff on the new Python files and `git diff --check` pass. The runner pins `jev-1.13.0` and rejects another model or an input usage over the reserved 64,000 tokens. A shared ledger reserves that model maximum per call before egress at the current published US$0.042/M input price; multiple independent ledgers do not form a fleet-wide cap.
- Remaining for WP-10: deployed browser receipt capture, real snapshot privacy review, accessible TypeSafe key/network, first hand-checked response, labelled held-out evaluation, and one durable ledger across runners. Current Vercel environment-variable scope is still unverified: the cloud browser reached a Google passkey step in the Vercel sign-in chain and then its browser connection failed. No key value was viewed.

## Browser receipt connection
- Added `dashboard/e2e/mission-control-receipt.spec.ts` and `scripts/mission_control_shadow_check.py`. One local command now runs Playwright against synthetic Pi-CEO responses, writes a JSONL browser snapshot, and runs the offline advisory replay. The runner's output contains no page text and has the same SHA as the snapshot. The dashboard ignores generated Playwright files.
- Success path: the browser check passed, six intercepted API responses had no 4xx/5xx, and J1/J4 were `NOT_EVALUATED` without a TypeSafe call. Snapshot and advisory receipt share HEAD `ded1a54` and `workspace_dirty: true`; no page text appears in the advisory output. Injected-failure path: Playwright exited 1, the wrapper preserved that failure, and the snapshot still reached the advisory runner with J1/J2/J4 marked `NOT_EVALUATED`. The model cannot turn a failing browser check green. Typecheck and lint passed (two existing warnings).
- Final local build gate repeated on a compiled Next.js app: dashboard **514 passed**, typecheck, lint 0 errors (two existing warnings), and build passed; Playwright 1 passed against `next start`, offline replay 1 record `NOT_EVALUATED`; Python **13 passed**, touched Python Ruff passed, and `git diff --check` passed. Prior broad backend and swarm results remain at the earlier commit and are not claimed as fresh for this slice.

SPM spec complete. Next safe action: run the seven isolation cases and the repo gate on a capable host, then review this branch at its exact commit before activation.

## 29 Sept release continuation
- Rebasing the seven local Mission Control commits onto `origin/main` at `cbed09c` resolved one documentation overlap in `docs/plans/mission-control/README.md`; the newer r3 plan and local shadow-runner note were both retained.
- Reconciled the synthetic Jev shadow runner with the founder's recorded no-daily-cap decision in `docs/plans/nexus-release-harness/adoption.md` O5. It now records each attempted call and measured input cost, with an optional cap only when configured. No live TypeSafe call was made.
- Focused backend verification after rebase: 36 passed (`test_mission_control_jev_shadow.py` and `test_pipeline_routes.py`); touched Python files pass Ruff. Dashboard: 578 passed across 66 files, typecheck passed, production build passed with local placeholders. Compiled browser receipt: 1 passed with synthetic responses, zero live Jev evaluations, offline advisory record retained.
- The broad backend suite was stopped by automatic approval review because it might contact a production Railway service with unverified test payload. Do not treat its partial progress as a pass or route around that rejection. Seven nested bubblewrap cases also require a host that supports isolation.
- Release state remains review only: no deployed SHA, real backend read journey, live Jev evaluation, independent release score, or human merge approval for this branch.
- PR #828 first preview build reached Vercel READY, but GitHub's Smoke Surface Gate failed because new interactive `/control` components lacked a new declaration. Added an authenticated `/control` smoke entry with two body assertions. A local compiled server returned login 200 and `/control` 200 with both strings; `SURFACE_BASE_SHA=origin/main python .github/scripts/smoke_surface_gate.py` passed with five added interactive files.
