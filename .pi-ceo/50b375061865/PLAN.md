# Implementation Plan

**Session:** 50b375061865  
**Confidence:** 52%

**Risk notes:** Brief says 'BUG — Bug Fix' with no specific ticket or symptom. Plan targets four explicitly documented bugs in CLAUDE.md (rate-limit GC, do-while autonomy, workspace GC, cron debounce) as highest-probability targets. Lessons-learned mention a prior failed Linear-setup task — if the intended bug is something else entirely (e.g. a Linear API wiring issue or a dashboard regression), confidence drops to ~0.2. Triggers file may not actually contain the cron debounce logic; actual location should be confirmed in unit 1 recon before editing. All fixes are additive-minimal per surgical-changes policy.

## Unit 1: Diagnose: Read auth.py, autonomy.py, and routes/utils.py to confirm known bug state
**Files:** `app/server/routes/auth.py`, `app/server/autonomy.py`, `app/server/routes/utils.py`

## Unit 2: Fix rate-limit GC: prune stale IPs inline in check_rate_limit() to stop _req_log growing unbounded
**Files:** `app/server/routes/auth.py`
**Test scenarios:**
  - happy path: IPs with last_request >120 s ago are pruned on every 5-min interval tick inside check_rate_limit()
  - edge case: active IPs are never pruned mid-window
  - edge case: function with empty _req_log does not raise

## Unit 3: Fix autonomy do-while: replace bare asyncio.sleep loop with 10 s startup_delay so first poll fires quickly after Railway restart
**Files:** `app/server/autonomy.py`
**Test scenarios:**
  - happy path: first poll executes within 10 s of startup, not after full interval
  - edge case: if LINEAR_API_KEY is absent the skip is logged and surfaced in /health
  - edge case: subsequent polls still respect the full interval cadence

## Unit 4: Fix workspace GC: terminal-state sessions (complete/failed/killed/interrupted) are deleted from app/workspaces/ after GC_MAX_AGE and orphan dirs are also swept
**Files:** `app/server/routes/utils.py`
**Test scenarios:**
  - happy path: directory for a session in 'complete' state older than GC_MAX_AGE is removed
  - edge case: running session directories are never deleted
  - edge case: orphan dirs not referenced by _sessions are removed

## Unit 5: Fix cron trigger debounce: use abs() on elapsed time and fire overdue triggers within 10 s of boot to survive Railway redeploy resets
**Files:** `app/server/routes/triggers.py`
**Test scenarios:**
  - happy path: trigger with last_fired_at in the past by more than interval fires within 10 s of server boot
  - edge case: non-overdue triggers do not fire on boot
  - edge case: abs() prevents negative elapsed time from skipping a trigger

## Unit 6: Verify: run pytest and confirm no regressions
**Files:** `tests/`
**Test scenarios:**
  - happy path: all existing tests pass (3 pre-existing failures in test_sdk_phase2.py are expected and acceptable)
  - edge case: new logic in auth.py, autonomy.py, utils.py, triggers.py covered by at least one assertion each
