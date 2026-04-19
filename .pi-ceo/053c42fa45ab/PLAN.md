# Implementation Plan

**Session:** 053c42fa45ab  
**Confidence:** 52%

**Risk notes:** Brief specifies 'BUG — Bug Fix' without naming a specific bug. Plan assumes the highest-leverage defects called out explicitly in CLAUDE.md and lessons-learned: (1) _req_log GC, (2) autonomy do-while delay, (3) /health missing linear_api_key/last_tick, (4) health-check script false-positive alerting, (5) in-memory session loss. If a different specific bug was intended, units 1-5 should be scoped down to just that bug's file. scripts/health_check.py may not exist yet — unit 4 may require creating it rather than editing. Session persistence (unit 5) is a larger change; if app_factory.py already has a persistence hook, only sessions.py needs touching. Test files may need to be created if they do not yet exist.

## Unit 1: Rate-limit GC: prune stale IPs in auth.py
**Files:** `app/server/routes/auth.py`
**Test scenarios:**
  - happy path: after 120s of inactivity an IP key is pruned from _req_log on next check_rate_limit() call
  - edge case: active IP is never pruned even after 5 min interval elapses
  - edge case: pruning does not raise KeyError when _req_log is empty

## Unit 2: Autonomy do-while fix: 10s startup_delay so first poll fires on boot
**Files:** `app/server/autonomy.py`
**Test scenarios:**
  - happy path: first poll executes within 15s of server start rather than after full interval
  - edge case: skipped poll (missing LINEAR_API_KEY) is logged, not silently swallowed
  - edge case: startup_delay does not delay shutdown signal handling

## Unit 3: /health endpoint surfaces linear_api_key bool and last_tick timestamp
**Files:** `app/server/routes/health.py`
**Test scenarios:**
  - happy path: GET /health returns {linear_api_key: true, last_tick: <iso8601>, autonomy_will_fire: true} when key is set
  - edge case: GET /health returns {linear_api_key: false} when LINEAR_API_KEY is absent and still returns HTTP 200
  - edge case: last_tick is null (not missing key) when autonomy has never fired

## Unit 4: Health-check script consecutive-failure threshold and cooldown
**Files:** `scripts/health_check.py`
**Test scenarios:**
  - happy path: single transient failure does not trigger alert; alert fires only after 2 consecutive failures
  - edge case: state file persists between script invocations so consecutive count survives process restart
  - edge case: alert is suppressed if last alert was within 30-minute cooldown window

## Unit 5: Session state persistence: write-to-tmp-then-replace after every state change
**Files:** `app/server/routes/sessions.py`, `app/server/app_factory.py`
**Test scenarios:**
  - happy path: session status written to disk atomically after transition (pending→running→complete)
  - edge case: orphan workspace dirs not in _sessions are GC'd after GC_MAX_AGE
  - edge case: crash during write leaves no corrupt JSON (tmp file is not promoted)

## Unit 6: Smoke-test and pytest gate for all patched modules
**Files:** `tests/test_auth.py`, `tests/test_health.py`, `tests/test_autonomy.py`
**Test scenarios:**
  - happy path: python -m py_compile passes on all edited files
  - happy path: pytest tests/test_auth.py tests/test_health.py tests/test_autonomy.py -x -q exits 0
  - edge case: no pre-existing passing test is regressed by the changes
