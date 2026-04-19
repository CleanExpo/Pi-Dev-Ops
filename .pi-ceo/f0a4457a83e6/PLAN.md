# Implementation Plan

**Session:** f0a4457a83e6  
**Confidence:** 52%

**Risk notes:** Brief specifies 'BUG — Bug Fix' with no named bug. Plan targets the three most concrete bugs documented in CLAUDE.md: (1) _req_log memory leak in auth.py, (2) workspace GC not running for terminal sessions, (3) cron trigger last_fired_at reset on Railway redeploy. If the actual bug is something else entirely (e.g. a runtime crash reported in Railway logs, a dashboard UI regression, or an SDK stream hang), unit 1 reconnaissance should surface it and the remaining units should be re-scoped. Confidence is moderate because the target bug is unspecified.

## Unit 1: Diagnose active bugs from logs and recent changes
**Files:** `app/server/routes/auth.py`, `app/server/routes/sessions.py`, `app/server/routes/triggers.py`, `app/server/routes/health.py`, `.harness/model-policy-violations.jsonl`
**Test scenarios:**
  - happy path: read each file and confirm documented bug patterns are present in code
  - edge case: check if any recent commits already partially addressed these issues

## Unit 2: Fix _req_log memory leak in auth.py rate-limit GC
**Files:** `app/server/routes/auth.py`
**Test scenarios:**
  - happy path: check_rate_limit() prunes IPs with last request >120s ago every 5 min inline
  - edge case: pruning does not discard IPs currently within their rate-limit window
  - edge case: concurrent async calls do not corrupt the _req_log dict during pruning

## Unit 3: Fix workspace GC — delete terminal-state session dirs after GC_MAX_AGE
**Files:** `app/server/routes/sessions.py`, `app/server/routes/utils.py`
**Test scenarios:**
  - happy path: /api/gc deletes app/workspaces dirs for sessions in complete/failed/killed/interrupted state older than GC_MAX_AGE (4h)
  - edge case: orphan workspace dirs not referenced by _sessions are also removed
  - edge case: running sessions are never deleted regardless of age

## Unit 4: Fix cron trigger last_fired_at reset on Railway redeploy
**Files:** `app/server/routes/triggers.py`
**Test scenarios:**
  - happy path: triggers overdue at boot fire within 10s of startup (catch-up logic)
  - edge case: abs() used in debounce check so negative time deltas don't suppress firing
  - edge case: trigger that fired 30s before redeploy is not re-fired immediately on boot

## Unit 5: Add/update pytest tests covering all three bug fixes
**Files:** `tests/test_auth.py`, `tests/test_sessions.py`, `tests/test_triggers.py`
**Test scenarios:**
  - happy path: rate-limit GC test confirms stale IPs removed after threshold
  - happy path: workspace GC test confirms terminal-state dirs cleaned up
  - happy path: cron startup catch-up fires overdue trigger within 10s
  - edge case: all three fixes pass pytest -x -q with no regressions to existing tests
