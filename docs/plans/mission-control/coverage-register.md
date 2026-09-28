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
- **CONFLICTING** — code reading says it cannot work, or docs disagree.

## Register

| ID | Surface | User journey | Write action | Evidence state | Evidence | Treatment |
|---|---|---|---|---|---|---|
| MC-00 | Control shell (TopBar, ModelBadge, ProjectSelector, ActiveBuildStrip, Subnav) | See ZTE score, pick project, see running builds | — | CONFLICTING † | ZTE: `D/app/api/zte/route.ts` calls `/api/zte/score`; **no such backend route** exists under `app/server` (grep: no match), so the badge can only ever show the harness file or "unavailable" | INVESTIGATE (WP-03) |
| MC-01 | `/control` hub | Tiles, fleet heartbeats, idea Board packet, live feed | Idea intake, dispose, GO (`CC/IdeaPipelinePanel.tsx:75,91,105`) | PARTIAL | SS:14 (307), SS:259 (auth 200, key names only); `mission-control-live-feed.test.tsx`, `idea-pipeline-panel.test.tsx`, `tests/test_mission_control_live_*.py` | EXTEND (browser journey) |
| MC-02 | `/control/goal` | Pick/create project, state goal, analyse, review drafts, file to Linear | Create/archive project, analyse, file tickets | PARTIAL | SS:990; `goal*.test.ts` lib only; **no UI test** for `GoalTicketForm`, `GoalProjectPicker`, `GoalDraftReview`; POSTs deliberately unsmoked (SS:612) | EXTEND |
| MC-03 | `/control/swarm` | Watch autonomy; kill / resume swarm | Kill, resume (`CC/KillSwitchPanel.tsx:227,326`) | PARTIAL | SS:95, SS:475 (401 only); `kill-switch-auth.test.ts`; **no backend test** of `R/swarm.py` kill/resume by path | EXTEND |
| MC-04 | `/control/model` | Read model routing and provider health | — | PARTIAL | SS:70/81; `tests/test_model_fabric.py`; no panel test | EXTEND |
| MC-05 | `/control/health` | Pi-SEO scores → findings → "Fix with Claude" → log stream | Start build (`CC/HealthGrid.tsx:266`) | PARTIAL | SS:190/220/604; `fix-session-live.test.tsx`; no backend test for `scan_monitor` | EXTEND |
| MC-06 | `/control/roles` | Role roster from live sessions | — | PARTIAL | SS:227; `phase-cost-evidence.test.tsx` | EXTEND |
| MC-07 | `/control/build` | Repo URL + brief → start build → watch log → stop | Start, stop | PARTIAL | SS `build_lifecycle`; `build-launch.test.tsx`; `tests/test_sessions.py`; readiness-continuation.md:116 "runtime activation remains unverified" | EXTEND |
| MC-08 | `/control/runs` | Routine outcomes, refresh | — | PARTIAL | SS:197; no `RoutineTable` test | EXTEND |
| MC-09 | `/control/curator` | Pending Skill Curator proposals | — | PARTIAL | SS:136/902; no component or backend-route test | EXTEND |
| MC-10 | `/control/margot` | Asset matrix, preview, build packet | Build packet | CONFLICTING † → **REPAIRED in this change** | Every panel call is a sub-path of `/api/margot/assets`; the proxy listed only the bare path, so all were refused 403 (`D/lib/pi-ceo-proxy-allowlist.ts`). Fixed and tested here; still needs a live check | REPAIR (WP-01, done) → EXTEND |
| MC-11 | `/control/pipeline` | List spec pipelines, run, watch detail | Run | CONFLICTING † → **REPAIRED in this change** | Detail poll `/api/spec-pipeline/{id}` was not on the allowlist → 403. Fixed and tested here | REPAIR (WP-01, done) → EXTEND |
| MC-12 | `/control/terminal` | Pick a redacted tmux session, tail it | — | PARTIAL | SS:810/821; `tests/test_terminal_route.py`; SS:19 "live output founder-verified only" | EXTEND |
| MC-13 | `/command-centre` | Index of decks | — | STRUCTURAL_ONLY | Route-existence and auth-coverage tests; `scripts/route-exercise.mjs` link walk (handoff-loop only, not CI) | EXTEND |
| MC-14 | `/command-centre/hermes` | Read-only Hermes module mirror | — | STRUCTURAL_ONLY | Reads a local Hermes config (`D/lib/command-centre/control-panel.ts:76-92`); behaviour on Vercel unknown; no dedicated test | INVESTIGATE |
| MC-15 | `/command-centre/knowledge` | Wiki graph tile, YouTube intent tile, tool catalogue | — | PARTIAL | `command-centre-readonly.test.ts` | EXTEND |
| MC-16 | `/command-centre/providers` | Provider key presence cockpit | — | PARTIAL | SS:883 (200, no body assertion) | EXTEND |
| MC-17 | `/command-centre/wall` | Kiosk fleet wall | — | PARTIAL | SS:117/128; wall tests; `tests/test_mesh_fleet_endpoint.py` | EXTEND |
| MC-18 | `/command-centre/wiki-graph` | Force graph of wiki pages | — | CONFLICTING | QUEUE.md:47 says 500 (RA-7264, open); page now wraps the client in try/catch; 2026-09-11 handoffs report the gate READY. No record of a verified fix | INVESTIGATE (WP-04) |
| MC-19 | `/command-centre/youtube-intent` | Video intent catalogue | — | CONFLICTING | Reads `.harness/…/state.json` from local disk and links `http://localhost:7119` (page.tsx:27,49); not linked from the index. On a deployed host the file is not expected to exist | INVESTIGATE |

## Coverage report

Counts reported separately, per the coverage rules:

| Measure | Count |
|---|---|
| Surfaces accounted for | 20 of 20 (19 pages + shell) |
| VERIFIED (observed user outcome on a named deploy) | **0** |
| PARTIAL | 13 |
| STRUCTURAL_ONLY | 2 |
| CONFLICTING | 5 (2 repaired in this change, pending live check) |
| Surfaces with a write action | 7 (MC-01, 02, 03, 05, 07, 10, 11) |
| Browser tests touching any surface | 0 |
| Unit tests in the Mission Control subset | ≈226 pytest (288 matched, 62 loosely related) + 214 vitest cases — all mocked |

A 100% accounting rate here coexists with zero verified user outcomes. That is the finding.
