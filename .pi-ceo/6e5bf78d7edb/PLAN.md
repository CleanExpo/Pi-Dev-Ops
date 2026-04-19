# Implementation Plan

**Session:** 6e5bf78d7edb  
**Confidence:** 35%

**Risk notes:** Brief states HOTFIX URGENT but does not name the specific production failure. Plan assumes the three highest-probability failure classes from CLAUDE.md: (1) rate-limit _req_log memory leak in auth.py, (2) in-memory session loss on restart in sessions.py, (3) /health returning 200 when autonomy loop is silently broken. Unit 4 is intentionally left broad — the actual file(s) to patch will be determined during units 1-3 diagnosis. If the real failure is in webhooks.py (self-referential push loop) or the SDK stream timeout in pipeline.py, unit 4 scope must be narrowed accordingly. Confidence is low because no reproduction steps or error logs were provided.

## Unit 1: Reproduce and triage: identify failure from health endpoint and recent logs
**Files:** `app/server/routes/health.py`, `app/server/app_factory.py`
**Test scenarios:**
  - happy path: GET /health returns 200 with autonomy_loop boolean and last_tick timestamp
  - edge case: GET /health still returns when LINEAR_API_KEY is missing — must surface linear_api_key: false not 200-silent

## Unit 2: Diagnose rate-limit GC memory leak in auth — _req_log accumulates stale IP keys
**Files:** `app/server/routes/auth.py`
**Test scenarios:**
  - happy path: check_rate_limit prunes IPs with last request >120s every ~5 min inline
  - edge case: cloud mode trusts X-Forwarded-For first entry; local mode uses request.client.host

## Unit 3: Diagnose session persistence — in-memory _sessions lost on restart, atomic disk writes
**Files:** `app/server/routes/sessions.py`
**Test scenarios:**
  - happy path: session state written to disk atomically (write-to-.tmp then os.replace) after every state change
  - edge case: terminal states (complete/failed/killed) GC'd after GC_MAX_AGE from app/workspaces/

## Unit 4: Apply minimal targeted fix to identified root cause file(s)
**Files:** `app/server/routes/auth.py`, `app/server/routes/sessions.py`, `app/server/routes/health.py`
**Test scenarios:**
  - happy path: fix compiles cleanly — python -m py_compile passes on all edited files
  - edge case: fix does not alter any file not directly related to the identified failure

## Unit 5: Regression gate — run pytest suite and import check
**Files:** `tests/`
**Test scenarios:**
  - happy path: python -c 'from app.server.main import app' succeeds
  - happy path: python -m pytest tests/ -x -q passes with expected 3 pre-existing failures in test_sdk_phase2.py only
  - edge case: no new test failures introduced by the fix

## Unit 6: Conventional commit staged diff — fix: <component> <description>
**Files:** `app/server/routes/auth.py`, `app/server/routes/sessions.py`, `app/server/routes/health.py`
