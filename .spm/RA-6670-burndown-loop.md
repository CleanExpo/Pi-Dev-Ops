# SPM Spec — RA-6670: Bounded daily P3 backlog-burndown loop

**Status:** build-ready · **Author:** SPM (Pi-Dev-Ops) · **Date:** 2026-06-29
**Ticket:** [RA-6670](https://linear.app/unite-group/issue/RA-6670) (High, In Progress, founder-reported 2026-06-15)
**Branch:** `phillmcgurk/ra-6670-close-the-cron-loop-bounded-daily-backlog-burndown-for-p3`
**Related:** RA-6774 (autonomous Kanban controller), RA-1966 (spend axes), RA-2027 (`discovery_archive`)

---

## 1. Task
Build a bounded daily cron trigger (`burndown`) that pulls the top-K open **P3** findings, drives each to a *terminal* state (PR-linked **or** closed-with-reason), and bounds spend — closing the gap where 88% of auto-filed findings are never worked.

## 2. Project context
The swarm has a **push side** (5 trigger types file findings as Linear tickets) and a **work side** (only `autonomy.py`, which fetches Urgent+High = priority ≤ 2). Scan findings default to **P3** (`triage.py:340`, medium→3). Result: tickets pile up at P3 and the only worker never touches them.

## 3. Problem (evidence — verified this session against live code)
- **Worker filter:** `app/server/autonomy.py:293` — `fetch_todo_issues()` = "Fetch Urgent + High priority Todo issues" (priority ≤ 2). ✅ verified.
- **Push→P3:** `app/server/triage.py:340` `_SEVERITY_TO_LINEAR_PRIORITY` = {critical:1, high:2, medium:3, low:4, info:4}; applied at `:451` with default 4. ✅ verified.
- **Backlog snapshot (ticket, founder-reported):** 250 open — P1=4, P2=26 (worked), **P3=219, P4=1 → 220 ignored = 88%**. `UNSUPPORTED` live-count (not re-queried this session; treat as directional, re-confirm at build start).
- **No burndown trigger exists** — `cron_triggers.py:389-422` dispatch chain has scan/monitor/intel_refresh/board_meeting/scout/feedback_loop/meta_curator/portfolio_pulse/discovery/discovery_archive/build, **no `burndown`**. ✅ greenfield confirmed.

## 4. Desired outcome
A daily cron run works/closes up to K P3 findings within a hard spend cap, never floods, and emits one edge-triggered Telegram line. After one week, **P3 open count trends down** and every touched ticket is terminal (PR or closed).

## 5. Scope
**In:** new `_fire_burndown_trigger`; `burndown` dispatch branch; top-K P3 fetch + rank + in-flight dedup; per-ticket work-vs-close decision; spend guard; edge-triggered Telegram; Hermes cron registration; tests.
**Out (explicitly rejected):** lowering the autonomy threshold to P3 (would spawn 219 sessions at once — flood + uncapped Max-plan spend). Re-enabling the disabled "Discovery loop" (that is a *push* loop — makes the problem worse). New finding sources. P4 handling (P3 only this pass).

## 6. Existing capability (reuse — do not rebuild)
| Need | Reuse |
|---|---|
| Trigger dispatch | `cron_triggers.py:389` `if/elif trigger_type ==` chain |
| Per-ticket build session | `autonomy.py` `create_session()` + `linear_todo_poller()` pattern |
| Ticket fetch / Linear GQL | `autonomy.py` `fetch_todo_issues()`, `_gql()`, `transition_issue()`, `comment_on_issue()`, `add_label_to_issue()` |
| Per-ticket prep | `autonomy.py` `_extract_repo_url()`, `_build_brief()`, `_infer_intent()`, `_infer_scope()`, `_should_skip_no_code()` |
| Close-with-reason | `discovery_archive.py` `_close_to_canceled(issue_id, state_id, comment)`, `_resolve_canceled_state_id(team_id)`, `ArchiveReport` |
| Spend bound | RA-1966 `TAO_MAX_COST_USD`, `TAO_HARD_STOP_FILE` (`config.py`, `kill_switch.py`, enforced in `orchestrator.py`) |
| Edge-triggered Telegram | existing watchdog pattern `autonomy.py:174` `_send_watchdog_telegram()` (per [[feedback-alert-noise-edge-trigger]]) |

## 7. Specialist board
- **PM:** highest-leverage open ticket; directly answers founder "no progress on evidence found." Ship the smallest loop that moves the P3 count.
- **Architect:** pure composition of existing parts; new code is one trigger fn + one dispatch line + one P3-fetch variant. No new subsystem. Risk: contention with `autonomy.py` on the same boards → dedup against in-flight session IDs (reuse `_is_pi_ceo_orphan`/`live_session_ids`).
- **Security:** no new external surface; spend is the attack surface — hard-cap K and reuse the existing kill-switch before every session.
- **QA:** acceptance is measurable (P3 trend + terminal-state invariant). Unit-test rank, cap, work-vs-close branch, dedup, and spend-stop with mocked Linear.
- **Devil's advocate:** *Is the value heuristic worth it?* No — start with recency-only ranking; a "value" score is speculative (CLAUDE.md §2). *Will it auto-close real work?* Risk — so close only the safe class (see §9 decision rule) and label, never silently delete.

## 8. Judge challenge — **score 88/100 → APPROVE BUILD**
Founder-reported, evidence-backed, greenfield, all dependencies verified present, measurable acceptance. Points off: (a) live P3 count not re-verified this session; (b) work-vs-close auto-decision carries a false-close risk. Both mitigated in §9. Above 85 → build (not a reduced experiment).

## 9. Proposed solution
New `app/server/burndown.py` (or extend `cron_triggers.py`) exposing `async def _fire_burndown_trigger(trigger, log)`:

1. **Fetch** open Todo issues at `priority == 3` across portfolio projects (new `fetch_burndown_candidates(api_key, cap)` — a `fetch_todo_issues` variant: same GQL, `priority: { eq: 3 }`, `state.type: unstarted`).
2. **Rank** by recency (`updatedAt` desc) — *recency only* for v1. Take top **K** (`TAO_BURNDOWN_DAILY_CAP`, default 5).
3. **Dedup** against in-flight session IDs (reuse autonomy's live-session set) — skip any already being worked.
4. **Per-ticket decision rule:**
   - **Work** (`create_session()` → PR) when `_extract_repo_url()` resolves AND `_should_skip_no_code()` is False.
   - **Close-to-Canceled** with a one-line reason via `_close_to_canceled()` when no repo URL resolves OR `_should_skip_no_code()` is True (non-code/ambiguous) — i.e. only the *provably-unworkable* class is auto-closed. Everything else is worked, never silently closed.
5. **Spend guard:** before each `create_session()`, check `TAO_HARD_STOP_FILE` + accumulated `TAO_MAX_COST_USD` (reuse `kill_switch`); stop the run cleanly if tripped.
6. **Dispatch:** add `elif trigger_type == "burndown":  # RA-6670` → `await _fire_burndown_trigger(trigger, log)` at `cron_triggers.py:~414`.
7. **Telegram:** one edge-triggered line per run — `RA-6670 burndown: {worked} worked / {closed} closed / {skipped} skipped` — only when counts changed vs last run (state file), per [[feedback-alert-noise-edge-trigger]].
8. **Cron registration:** add a daily `burndown` Hermes cron entry (push side) — document the exact entry in the PR.

## 10. UX
No UI. Operator-facing surface = the edge-triggered Telegram line + Linear ticket state changes (each touched ticket shows a PR link or a Canceled+comment). Optional follow-up: surface counts on the Mission Control Panel (RA-6474) — out of scope here.

## 11. Technical notes
- **Priority filter:** Linear GQL `issues(filter: { priority: { eq: 3 }, state: { type: { eq: "unstarted" } } })`. Confirm `eq` vs `lte` against the existing `fetch_todo_issues` query shape.
- **Cap env:** `TAO_BURNDOWN_DAILY_CAP` (int, default 5) in `config.py` alongside the RA-1966 axes.
- **State file** for edge-triggered Telegram: a small JSON under `.harness/` — **must be gitignored** (per [[routines-worktree-pinned-main]] / RA-3006 the `.harness` mutation-tracking trap; add to `.gitignore` in the same PR if not already covered).
- **Idempotency:** a second run the same day must not re-pick a ticket already moved to In Progress / Canceled (dedup covers this; verify Canceled is excluded by the `unstarted` state filter).

## 12. Security
No new endpoints or secrets. `LINEAR_API_KEY` already in env. Only mutation is ticket transitions/comments + build sessions — all already audited paths. The one new risk is **spend**; bounded by K + kill-switch reuse. No auto-delete (close-to-Canceled is reversible).

## 13. Verification (must actually run — evidence policy)
- `pytest tests/test_burndown.py` (new) — green.
- Full `pytest` suite green (no regression in `test_autonomy*`, `test_cron_triggers*`, `test_discovery_archive`).
- Dry-run: `_fire_burndown_trigger` with `TAO_BURNDOWN_DAILY_CAP=0` → fetches, picks nothing, exits clean (proves wiring without spend).
- Live-count re-confirm at build start: query open P3 count, record actual number in the PR (replaces the `UNSUPPORTED` snapshot).

## 14. Loop + stress testing
- **Rank/cap:** 50 mock P3 tickets, K=5 → exactly 5 most-recent picked.
- **Work-vs-close branch:** ticket w/ repo URL → `create_session` called; ticket w/o repo URL → `_close_to_canceled` called; `_should_skip_no_code`=True → closed.
- **Dedup:** ticket already in live-session set → skipped (neither worked nor closed).
- **Spend stop:** `TAO_HARD_STOP_FILE` present → run halts before first session, count=0.
- **Edge-trigger:** two identical runs → second sends NO Telegram (counts unchanged).
- **Idempotency:** re-run same day → already-moved tickets not re-picked.

## 15. Acceptance criteria (from ticket, sharpened)
1. New `burndown` trigger dispatches and runs end-to-end on a real cron tick.
2. Each run touches ≤ K tickets; every touched ticket ends **terminal** (PR-linked OR Canceled-with-comment) — none left in Todo.
3. Run respects `TAO_BURNDOWN_DAILY_CAP` and halts on kill-switch / `TAO_MAX_COST_USD`.
4. Telegram fires once per run, edge-triggered only.
5. After 1 week of daily runs, **open P3 count trends down** (measured from the build-start baseline recorded in the PR).
6. Full test suite green; new `test_burndown.py` covers §14.

## 16. /goal command
```
/goal Implement RA-6670 — bounded daily P3 backlog-burndown trigger in Pi-Dev-Ops.

Branch: phillmcgurk/ra-6670-close-the-cron-loop-bounded-daily-backlog-burndown-for-p3
Spec: .spm/RA-6670-burndown-loop.md (follow it; do not expand scope).

Build until ALL acceptance criteria in spec §15 are met and verification §13 actually runs green:
1. Re-confirm live open-P3 count; record it in the PR body as the baseline.
2. Add `TAO_BURNDOWN_DAILY_CAP` (default 5) to app/server/config.py.
3. Add `fetch_burndown_candidates()` (P3/unstarted variant of fetch_todo_issues) + `_fire_burndown_trigger()` reusing autonomy.create_session and discovery_archive._close_to_canceled per spec §9.
4. Wire `elif trigger_type == "burndown"` into cron_triggers.py dispatch (~line 414).
5. Edge-triggered Telegram one-liner; state file gitignored under .harness/.
6. Write tests/test_burndown.py covering spec §14; run full pytest green.
7. Register the daily `burndown` Hermes cron entry; document it in the PR.
8. Open PR linking RA-6670. Do NOT lower the autonomy priority threshold.

Verify: pytest green + cap=0 dry-run clean. Commit, push, open PR. Report the live P3 baseline.
```

## 17. Implementation sequence
1. `config.py` cap env → verify import. 2. `fetch_burndown_candidates()` + unit test (mock GQL). 3. `_fire_burndown_trigger()` work-vs-close + dedup + spend guard. 4. Dispatch branch. 5. Edge-triggered Telegram + gitignored state file. 6. `test_burndown.py` (§14) + full suite. 7. cap=0 dry-run. 8. Hermes cron entry. 9. PR with live P3 baseline.

## 18. Session-handoff seed
- **Goal:** ship RA-6670 burndown loop to a merged PR with passing CI.
- **Branch:** `phillmcgurk/ra-6670-...` (create from current clean `main` @ `28c56c08`).
- **Key files:** `app/server/cron_triggers.py` (dispatch :389), `app/server/autonomy.py` (`create_session`, `fetch_todo_issues:292`), `app/server/discovery_archive.py` (`_close_to_canceled:141`), `app/server/triage.py:340`, `app/server/config.py`, new `tests/test_burndown.py`.
- **First command:** `cd /Users/phill-mac/Pi-Dev-Ops && git checkout -b phillmcgurk/ra-6670-close-the-cron-loop-bounded-daily-backlog-burndown-for-p3`
- **Risk notes:** don't lower autonomy threshold; gitignore the new state file (RA-3006 trap); re-verify P3 count before claiming the baseline.

## 19. Final recommendation
**APPROVE BUILD (88/100).** Highest-leverage open ticket, all dependencies verified present in the live tree, pure composition, measurable acceptance. Build on a fresh branch off `main`; the only judgment call deferred to build time is the auto-close safe-class boundary (§9) — keep it conservative (close only no-repo / no-code).

SPM spec complete. Next safe action: run the §16 `/goal` command on a fresh `phillmcgurk/ra-6670-...` branch to implement the burndown loop.
