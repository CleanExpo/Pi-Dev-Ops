# Mission Control — work packages to reach AAA

Dependency-ordered. Each package names the register rows it moves, its evidence of completion,
and its authority class: **SAFE** (reversible code/test change, agent may do it), **SECRET**
(needs a credential only Phill can supply), **FOUNDER** (money, production switch or direction).

| ID | Outcome | Rows | Depends on | Authority | Completion test |
|---|---|---|---|---|---|
| WP-01 | Margot panel and Spec-pipeline detail stop being refused by the dashboard proxy | MC-10, MC-11 | — | SAFE | **Done in this change.** `dashboard/lib/pi-ceo-proxy-allowlist.ts` + test that fails on the old list and passes on the new (8/8); full vitest 504/504, `tsc` clean. Live check still owed (WP-06) |
| WP-02 | Playwright can sign in to a deployed dashboard | all | secret | SECRET | A second Playwright project (`control-live`) with `baseURL` from env, signing in with `DASHBOARD_PASSWORD` stored as a GitHub Actions secret; one test opens `/control` and sees the hub. The existing `playwright.config.ts` targets only a local stub server and `/placecards-prototype.html` |
| WP-03 | ZTE badge reads a real score or says honestly that none exists | MC-00 | — | SAFE | Investigation first: `dashboard/app/api/zte/route.ts` calls `/api/zte/score`, which no backend route serves. Decide: add the route (reusing the tested ZTE score library) or remove the backend branch. Test that the badge's source label matches reality |
| WP-04 | wiki-graph status settled | MC-18 | WP-02 | SAFE | Browser test on production opens `/command-centre/wiki-graph` and records 200 + rendered graph or an explicit error; close or re-open RA-7264 with that receipt |
| WP-05 | Deploy-only pages behave honestly on Vercel | MC-14, MC-19 | WP-02 | SAFE | `hermes` reads a local config file; `youtube-intent` reads `.harness/…/state.json` and links `http://localhost:7119`. On a deployed host these must show an explicit "not available on this host" state, not a broken or empty page. Browser assertion per page |
| WP-06 | Tier A read journeys for all 20 rows | all | WP-02 | SAFE | One spec per surface: real-data assertion (check 1) + zero unexpected 4xx/5xx (check 2) + receipt (check 4) |
| WP-07 | Tier A write journeys against PR preview | MC-01, 02, 03, 05, 07, 10, 11 | WP-02 | SAFE for preview; **FOUNDER** for any that would file to the real Linear workspace or start a paid build | Each write completes and survives reload on the Railway `Pi-Dev-Ops-pr-<n>` + Vercel preview pair; side effects cleaned up |
| WP-08 | Component tests for the 8 untested panels | MC-02, 04, 08, 09, 10, 11, 12 | — | SAFE | vitest loaded/empty/error cases for `GoalTicketForm`, `GoalProjectPicker`, `ModelFabricPanel`, `RoutineTable`, `CuratorProposalsPanel`, `MargotAssetsPanel`, `SpecPipelinePanel`, `TerminalPanel` |
| WP-09 | Tier AA failure-path, auth, a11y and phone viewport | all | WP-06 | SAFE | Checks 5, 6, 8, 9 per surface. Adds `@axe-core/playwright` (new dev dependency, no cost) |
| WP-10 | Jev evaluator (shadow) | all | WP-06; **SECRET** (`TYPESAFE_API_KEY` in GitHub Actions) or environment allowlist | SECRET | Script reads run snapshots, redacts, calls J1–J4, writes JSONL; budget guard stops at $4/day; 60-snapshot labelled set reports held-out accuracy |
| WP-11 | Nightly production run + scorecard | all | WP-06, WP-09 | SAFE | Scheduled workflow runs the suite against production, uploads receipts, computes per-surface tier by the rules in [aaa-rating.md](aaa-rating.md), publishes the scorecard |
| WP-12 | AAA reached | all | WP-01…11 | — | Three consecutive nightly runs meet every AAA check; register has no CONFLICTING/STRUCTURAL_ONLY row |

## Founder items that sit outside these packages

These affect "finished" for the wider system, not the AAA grade of the screens themselves:

- **D0 — merge authority.** Cross-model audit (10 Sept) or human-merge-only
  (`docs/session-handoffs/20260911-1230-0eca2639.md:212`). PR #808 was squash-merged by auto-merge
  after a Cursor bot approval on 28 Sept, which suggests the former is in practice; the written record
  still says the latter.
- **Autonomy switch.** `TAO_AUTONOMY_ENABLED` was `0` in production on 2026-08-18 (QUEUE.md:24-34);
  current value not re-checked.
- **Secrets.** `DASHBOARD_PASSWORD` and `TYPESAFE_API_KEY` as GitHub Actions secrets (WP-02, WP-10).

## Refinement checkpoints

After WP-06's first run, re-open this plan: the register rows move from PARTIAL to VERIFIED or to
CONFLICTING based on what the browser actually saw, and WP-07+ are re-sized from those results.
