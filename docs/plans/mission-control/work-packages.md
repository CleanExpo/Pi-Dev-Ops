# Mission Control — work packages to reach AAA (MC track)

Dependency-ordered. Each package names the register rows it moves, its evidence of completion,
and its authority class: **SAFE** (reversible code/test change, agent may do it), **SECRET**
(needs a credential only Phill can supply), **FOUNDER** (money, production switch or direction).

| ID | Outcome | Rows | Depends on | Authority | Completion test |
|---|---|---|---|---|---|
| WP-01 | Margot panel and Spec-pipeline detail stop being refused by the dashboard proxy | MC-10, MC-11 | — | SAFE | **Done in this change.** `dashboard/lib/pi-ceo-proxy-allowlist.ts` + test that fails on the old list and passes on the new (8/8); full vitest 504/504, `tsc` clean. Live check still owed (WP-06) |
| WP-02 | Playwright can sign in to a deployed dashboard | all | secret | SECRET | A second Playwright project (`control-live`) with `baseURL` from env, signing in with `DASHBOARD_PASSWORD` stored as a GitHub Actions secret; one test opens `/control` and sees the hub. The existing `playwright.config.ts` targets only a local stub server and `/placecards-prototype.html` |
| WP-03 | ZTE badge reads a real score or says honestly that none exists | MC-00 | — | SAFE | **Done in #818 (awaiting merge).** Added `app/server/routes/zte.py` serving the daily cron's cached score, 404 when none; `tests/test_zte_score_route.py` 6 tests. Live check owed after merge (badge shows `source: backend`) |
| WP-04 | wiki-graph status settled | MC-18 | WP-02 | SAFE | Browser test on production opens `/command-centre/wiki-graph` and records 200 + rendered graph or an explicit error; close or re-open RA-7264 with that receipt |
| WP-05 | Deploy-only pages behave honestly on Vercel | MC-14, MC-19 | — | SAFE | **youtube-intent done in #818 (awaiting merge):** explicit "Not available on this host" state, no localhost link in production. `hermes` was re-checked and does **not** read a local file, so it needs no change here. Browser assertion per page moves into WP-06 |
| WP-06 | Level 1 read journeys for all 20 rows | all | WP-02 | SAFE | One spec per surface: real-data assertion (check 1) + zero unexpected 4xx/5xx (check 2) + receipt (check 4) |
| WP-07 | Level 1 write journeys against PR preview | MC-01, 02, 03, 05, 07, 10, 11 | WP-02 | SAFE for preview; **FOUNDER** for any that would file to the real Linear workspace or start a paid build | Each write completes and survives reload on the Railway `Pi-Dev-Ops-pr-<n>` + Vercel preview pair; side effects cleaned up |
| WP-08 | Component tests for the 8 untested panels | MC-02, 04, 08, 09, 10, 11, 12 | — | SAFE | vitest loaded/empty/error cases for `GoalTicketForm`, `GoalProjectPicker`, `ModelFabricPanel`, `RoutineTable`, `CuratorProposalsPanel`, `MargotAssetsPanel`, `SpecPipelinePanel`, `TerminalPanel` |
| WP-09 | Level 2 failure-path, auth, a11y and phone viewport | all | WP-06 | SAFE | Checks 5, 6, 8, 9 per surface. Adds `@axe-core/playwright` (new dev dependency, no cost) |
| WP-10 | Jev evaluator (shadow) | all | WP-06; **SECRET** (`TYPESAFE_API_KEY` in GitHub Actions) or environment allowlist | SECRET | Script reads run snapshots, redacts, calls J1–J4, writes JSONL; spend ledgered per call, no daily cap (founder, 28 Sept; conflicts with the packet's budget rule — adoption.md O5, open); 60-snapshot labelled set reports held-out accuracy |
| WP-11 | Nightly production run + scorecard | all | WP-06, WP-09 | SAFE | Scheduled workflow runs the suite against production, uploads receipts, computes each surface's level by the rules in [aaa-rating.md](aaa-rating.md), publishes the scorecard |
| WP-12 | Level 3 reached | all | WP-01…11 | — | Three consecutive nightly runs meet every Level 1–3 check; register has no CONFLICTING/STRUCTURAL_ONLY row. **Not AAA on its own:** the portfolio rubric also needs the items listed in aaa-rating.md (two non-author audits, promise register, support, recovery) |

## Founder items that sit outside these packages

These affect "finished" for the wider system, not the MC levels of the screens themselves:

- **D0 — merge authority. Decided 28 Sept 2026 (RA-7818): human merge only.** A cross-model audit
  is review evidence, not acceptance.
- **Jev budget.** Whether "no daily cap" overrides the packet's recorded-budget rule
  ([adoption.md O5](../nexus-release-harness/adoption.md)). Until decided, Jev runs dry only.
- **Autonomy switch.** `TAO_AUTONOMY_ENABLED` was `0` in production on 2026-08-18 (QUEUE.md:24-34);
  current value not re-checked.
- **Secrets.** `DASHBOARD_PASSWORD` and `TYPESAFE_API_KEY` as GitHub Actions secrets (WP-02, WP-10).

## Refinement checkpoints

After WP-06's first run, re-open this plan: the register rows move from PARTIAL to VERIFIED or to
CONFLICTING based on what the browser actually saw, and WP-07+ are re-sized from those results.

## Place in the portfolio harness (NEXUS-RELEASE-HARNESS v1.0)

These packages are the MC track's instance of the packet's per-product chain
`P-DISCOVER → P-PROMISE → P-VERIFY → P-REPAIR → P-AUDIT → P-RELEASE → P-OBSERVE`
([adoption decision O3](../nexus-release-harness/adoption.md)). They keep their numbers; nothing is
re-ticketed.

| Chain step | MC packages | State |
|---|---|---|
| MC-DISCOVER | [coverage-register.md](coverage-register.md) (20 rows) | Shallow pass done; deep runtime pass needs WP-02 |
| MC-PROMISE | [promise-register.md](promise-register.md) — 12 nav blurbs and 21 button promises, each with source line and proving journey | Written 29 Sept: 33 promises, 0 proven, 20 with a mocked test |
| MC-VERIFY | WP-02, WP-04, WP-06, WP-07, WP-09 | Blocked on `DASHBOARD_PASSWORD` (RA-7832) |
| MC-REPAIR | WP-01, WP-03, WP-05, WP-08 | Done (#809 merged; #818 awaiting merge) |
| MC-AUDIT | *new:* two non-author audits of the final candidate (Claude + Codex lanes) | NOT_RUN; Codex lane unavailable in this container |
| MC-RELEASE | WP-12 + packet release stages R0–R4 and support readiness (RANA) | NOT_STARTED |
| MC-OBSERVE | WP-11 nightly run and scorecard; WP-10 Jev triage as the CP-04 advisory adapter | WP-10 prep done; rest blocked |

Portfolio packages this track depends on: **CP-00** (authority/identity reconcile), **CP-03**
(test environment and provider-lane admission — covers both RA-7832 secrets), **CP-04** (evidence
adapter; the idea-to-live gaps RA-7811–RA-7822 feed it), **CP-07** (staged release + RANA handover).
