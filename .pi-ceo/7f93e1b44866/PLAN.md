# Implementation Plan

**Session:** 7f93e1b44866  
**Confidence:** 42%

**Risk notes:** Brief specifies 'BUG — Bug Fix' with no specific bug identified. Plan targets the three bugs explicitly documented as known issues in CLAUDE.md: (1) _req_log unbounded growth in auth.py, (2) /health silent-success when LINEAR_API_KEY missing, (3) autonomy do-while first-poll delay. If the actual bug is unrelated to these (e.g. a frontend crash, SDK hang, or push-phase failure), this plan will miss the target. Units 2-4 are independent and can be parallelised. Unit 6 depends on all fixes landing. Confidence is low due to ambiguous brief — executor should check Railway logs and recent GitHub Actions failures first to confirm which bug is live before applying fixes.

## Unit 1: Reproduce & diagnose: identify active bug from logs and recent changes
**Files:** `app/server/routes/auth.py`, `app/server/routes/health.py`, `app/server/routes/sessions.py`, `app/server/autonomy.py`
**Test scenarios:**
  - happy path: import check passes — python -c 'from app.server.main import app'
  - edge case: rate-limit _req_log grows unbounded under high request volume
  - edge case: /health returns 200 even when LINEAR_API_KEY is missing
  - edge case: autonomy loop skips first poll cycle after Railway restart

## Unit 2: Fix: rate-limit GC — prune stale IPs inline in check_rate_limit()
**Files:** `app/server/routes/auth.py`
**Test scenarios:**
  - happy path: stale IP keys older than 120s are pruned during check_rate_limit call
  - edge case: pruning does not affect IPs with recent requests
  - edge case: concurrent requests do not cause KeyError during pruning

## Unit 3: Fix: /health endpoint must surface linear_api_key bool and last tick timestamp
**Files:** `app/server/routes/health.py`
**Test scenarios:**
  - happy path: /health response includes linear_api_key: true when key is set
  - edge case: /health response includes linear_api_key: false and does not return 200 silently when key is absent
  - edge case: last_tick timestamp is present and recent when autonomy loop is running

## Unit 4: Fix: autonomy do-while — fire first poll within 10s of startup, log every skip
**Files:** `app/server/autonomy.py`
**Test scenarios:**
  - happy path: first poll fires within 10s of server startup instead of after full interval
  - edge case: skipped polls due to missing LINEAR_API_KEY emit a log entry per skip
  - edge case: interval continues correctly after startup catch-up tick

## Unit 5: Fix: cron trigger debounce — use abs() and fire overdue triggers within 10s of boot
**Files:** `app/server/routes/triggers.py`
**Test scenarios:**
  - happy path: overdue trigger fires within 10s of Railway redeploy
  - edge case: abs() in debounce prevents skipping triggers whose last_fired_at is in the future due to clock drift
  - edge case: triggers that are not overdue are not fired at startup

## Unit 6: Verify: run full test suite and smoke test against local server
**Files:** `tests/`, `scripts/smoke_test.py`
**Test scenarios:**
  - happy path: pytest tests/ -x -q passes with only the 3 pre-existing sdk_phase2 failures
  - happy path: smoke_test.py returns exit 0 against local uvicorn on port 7777
  - edge case: ruff lint passes on all modified files
