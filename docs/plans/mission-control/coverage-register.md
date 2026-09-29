# Mission Control — capability and journey coverage register

**Inspected revision:** `e3ea829` (main, 28 Sept 2026). **Method:** three read-only inventory
agents (surfaces, tests, open work), each row cited to file and line; the three code-read defects
marked † were re-checked by hand in this session. Evidence states follow
[completion-coverage.md](../plan-to-done-v1.1/plan-to-done/references/completion-coverage.md).

Paths: `D` = `dashboard/`, `CC` = `dashboard/components/control/`, `R` = `app/server/routes/`,
`SS` = `.github/smoke-surfaces.json`.

## What "evidence" means in this table

- **VERIFIED** — a named check passed against a named environment and revision. Nothing in this
  table reaches VERIFIED today: no browser test opens any Mission Control page (`D/e2e/` covers only
  `placecards-prototype.html`), and live smoke checks status codes and JSON key names, not what a
  user sees.
- **PARTIAL** — unit tests with mocks, or a live status-code smoke, but no observed user outcome.
- **STRUCTURAL_ONLY** — the page and route exist; nothing exercises them.
- **CONFLICTING** — a check failed on the current revision, or code reading says it cannot work.
  Sources that merely disagree, with no failing check, are UNKNOWN. Once receipts exist, rows are
  derived from them by the rules in [adoption.md §4.1](../nexus-release-harness/adoption.md).

## Register

| ID | Surface | User journey | Write action | Evidence state | Evidence | Treatment |
|---|---|---|---|---|---|---|
| MC-00 | Control shell (TopBar, ModelBadge, ProjectSelector, ActiveBuildStrip, Subnav) | See ZTE score, pick project, see running builds | — | PARTIAL — **repaired round 2**, live check owed | Was CONFLICTING: `dashboard/app/api/zte/route.ts` asked for `/api/zte/score`, which no backend route served. Round 2 added `app/server/routes/zte.py` serving the daily cron's `.harness/zte-v2-score.json` (score, band, computed_at, stale after 48 h; 404 when absent). `tests/test_zte_score_route.py` 6 tests | EXTEND (browser check: badge shows `source: backend`) |
| MC-01 | `/control` hub | Tiles, fleet heartbeats, idea Board packet, live feed | Idea intake, dispose, GO (`CC/IdeaPipelinePanel.tsx:75,91,105`) | PARTIAL | SS:14 (307), SS:259 (auth 200, key names only); `mission-control-live-feed.test.tsx`, `idea-pipeline-panel.test.tsx`, `tests/test_mission_control_live_*.py` | EXTEND (browser journey) |
| MC-02 | `/control/goal` | Pick/create project, state goal, analyse, review drafts, file to Linear | Create/archive project, analyse, file tickets | PARTIAL | SS:990; `goal*.test.ts` lib only; **no UI test** for `GoalTicketForm`, `GoalProjectPicker`, `GoalDraftReview`; POSTs deliberately unsmoked (SS:612) | EXTEND |
| MC-03 | `/control/swarm` | Watch autonomy; kill / resume swarm | Kill, resume (`CC/KillSwitchPanel.tsx:227,326`) | PARTIAL | SS:95, SS:475 (401 only); `kill-switch-auth.test.ts`; **no backend test** of `R/swarm.py` kill/resume by path | EXTEND |
| MC-04 | `/control/model` | Read model routing and provider health | — | PARTIAL | SS:70/81; `tests/test_model_fabric.py`; no panel test | EXTEND |
| MC-05 | `/control/health` | Pi-SEO scores → findings → "Fix with Claude" → log stream | Start build (`CC/HealthGrid.tsx:266`) | PARTIAL | SS:190/220/604; `fix-session-live.test.tsx`; no backend test for `scan_monitor` | EXTEND |
| MC-06 | `/control/roles` | Role roster from live sessions | — | PARTIAL | SS:227; `phase-cost-evidence.test.tsx` | EXTEND |
| MC-07 | `/control/build` | Repo URL + brief → start build → watch log → stop | Start, stop | PARTIAL | SS `build_lifecycle`; `build-launch.test.tsx`; `tests/test_sessions.py`; readiness-continuation.md:116 "runtime activation remains unverified" | EXTEND |
| MC-08 | `/control/runs` | Routine outcomes, refresh | — | PARTIAL | SS:197; no `RoutineTable` test | EXTEND |
| MC-09 | `/control/curator` | Pending Skill Curator proposals | — | PARTIAL | SS:136/902; no component or backend-route test | EXTEND |
| MC-10 | `/control/margot` | Asset matrix, preview, build packet | Build packet | PARTIAL — **repaired round 1** (#809), live check owed | Every panel call is a sub-path of `/api/margot/assets`; the proxy listed only the bare path, so all were refused 403 (`D/lib/pi-ceo-proxy-allowlist.ts`). Fixed and tested here; still needs a live check | REPAIR (WP-01, done) → EXTEND |
| MC-11 | `/control/pipeline` | List spec pipelines, run, watch detail | Run | PARTIAL — **repaired round 1** (#809), live check owed | Detail poll `/api/spec-pipeline/{id}` was not on the allowlist → 403. Fixed and tested here | REPAIR (WP-01, done) → EXTEND |
| MC-12 | `/control/terminal` | Pick a redacted tmux session, tail it | — | PARTIAL | SS:810/821; `tests/test_terminal_route.py`; SS:19 "live output founder-verified only" | EXTEND |
| MC-13 | `/command-centre` | Index of decks | — | STRUCTURAL_ONLY | Route-existence and auth-coverage tests; `scripts/route-exercise.mjs` link walk (handoff-loop only, not CI) | EXTEND |
| MC-14 | `/command-centre/hermes` | Read-only Hermes module mirror | — | PARTIAL | **Correction (round 2):** the round-1 claim that it reads a local config file was wrong — `lib/command-centre/control-panel.ts` is a static registry (`source: 'static_registry'`, no `fs` import; checked by `grep -n 'fs\.\|readFile' `), and the page already labels its values "Design target (not live)". Covered by `command-centre-readonly.test.ts` and the provenance map | EXTEND |
| MC-15 | `/command-centre/knowledge` | Wiki graph tile, YouTube intent tile, tool catalogue | — | PARTIAL | `command-centre-readonly.test.ts` | EXTEND |
| MC-16 | `/command-centre/providers` | Provider key presence cockpit | — | PARTIAL | SS:883 (200, no body assertion) | EXTEND |
| MC-17 | `/command-centre/wall` | Kiosk fleet wall | — | PARTIAL | SS:117/128; wall tests; `tests/test_mesh_fleet_endpoint.py` | EXTEND |
| MC-18 | `/command-centre/wiki-graph` | Force graph of wiki pages | — | CONFLICTING | QUEUE.md:47 says 500 (RA-7264, open); page now wraps the client in try/catch; 2026-09-11 handoffs report the gate READY. No record of a verified fix | INVESTIGATE (WP-04) |
| MC-19 | `/command-centre/youtube-intent` | Video intent catalogue | — | PARTIAL — **repaired round 2**, live check owed | Was CONFLICTING: on the deployed host the state file is absent, the API returned 200 with zeros, and the Knowledge tile showed a green *live* badge with "0 strategic signals"; the page showed a raw ENOENT with the server path and linked `localhost:7119`. Round 2: shared loader `lib/command-centre/youtube-intent-state.ts` (ok / absent / error), API adds `available`, tile goes degraded with "Not available on this host", localhost link only outside production. `__tests__/youtube-intent-state.test.tsx` (tile test fails on the old tile) | EXTEND |

## Coverage report

Counts reported separately, per the coverage rules:

| Measure | Count |
|---|---|
| Surfaces accounted for | 20 of 20 (19 pages + shell) |
| VERIFIED (observed user outcome on a named deploy) | **0** |
| PARTIAL | 18 (round 1: 13) |
| STRUCTURAL_ONLY | 1 — MC-13 (round 1: 2; MC-14 was mis-classified) |
| CONFLICTING | 1 — MC-18 wiki-graph (round 1: 5; MC-00, 10, 11, 19 repaired, pending live check) |
| Surfaces with a write action | 7 (MC-01, 02, 03, 05, 07, 10, 11) |
| Browser tests touching any surface | 1 spec built (`dashboard/e2e-live/control-hub.spec.ts`, MC-00); 0 live runs yet — needs `DASHBOARD_PASSWORD` in GitHub Actions |
| Unit tests in the Mission Control subset | ≈226 pytest (288 matched, 62 loosely related) + 214 vitest cases — all mocked |

A 100% accounting rate here coexists with zero verified user outcomes. That is the finding.

## Round 2 (29 Sept 2026, PR #818)

Component tests now exist for every panel the register listed as untested (WP-08): Goal picker and form (MC-02), Model Fabric (MC-04), Routines (MC-08), Curator (MC-09), Margot (MC-10), Spec pipeline (MC-11), Terminal (MC-12) — 59 cases. Four of those panels showed a failure as a normal state and were fixed, each with a test shown failing first: Model Fabric (500 → "DISABLED"), Curator (failed read → "No pending proposals"), Spec pipeline (outage → empty list), Margot (failed preview, packet list and packet expand did nothing). These rows stay PARTIAL: component tests use mocked responses, and Level 1 still needs the browser check on the deployed site (WP-02, blocked on `DASHBOARD_PASSWORD`, RA-7832).
