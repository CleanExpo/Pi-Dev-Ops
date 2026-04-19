# Implementation Plan

**Session:** 52cbfb296629  
**Confidence:** 42%

**Risk notes:** Brief specifies 'BUG — Bug Fix' without naming the specific bug or error class. Plan assumes the highest-probability failure modes from CLAUDE.md hardwired lessons: (1) _req_log memory leak in auth rate-limiter, (2) autonomy.py silent skip not surfaced in /health, (3) session state lost on restart, (4) parse_event crash on non-dict SDK events. If the actual bug is in a different subsystem (e.g. dashboard SSE, push layer, MCP server), units 2-5 should be re-targeted. Confidence lowered accordingly. Unit 6 is always valid as the verification gate. Recommend reading app/server/routes/ and recent git log before starting unit 2.

## Unit 1: Reproduce failure condition — audit recent changes and logs
**Files:** `app/server/routes/auth.py`, `app/server/routes/sessions.py`, `app/server/app_factory.py`, `app/server/autonomy.py`
**Test scenarios:**
  - happy path: identify exact traceback or silent-failure symptom from recent prod logs
  - edge case: confirm failure is not a transient restart artifact (check consecutive-failure threshold)

## Unit 2: Fix _req_log IP accumulation memory leak in auth rate-limiter
**Files:** `app/server/routes/auth.py`
**Test scenarios:**
  - happy path: IPs with last-request > 120s are pruned on each check_rate_limit() call
  - edge case: pruning logic does not evict an active IP mid-burst
  - edge case: cloud mode trusts X-Forwarded-For first entry, local mode uses request.client.host

## Unit 3: Fix autonomy.py silent skip when LINEAR_API_KEY missing — surface in /health
**Files:** `app/server/autonomy.py`, `app/server/routes/health.py`
**Test scenarios:**
  - happy path: /health returns linear_api_key: true and last_tick timestamp when key present
  - edge case: /health returns linear_api_key: false and surfaces skip reason when key absent
  - edge case: do-while pattern — first poll fires within 10s startup_delay, not after full interval

## Unit 4: Fix session state persistence — atomic write after every state change
**Files:** `app/server/routes/sessions.py`
**Test scenarios:**
  - happy path: session status survives server restart (written to disk atomically via tmp + os.replace)
  - edge case: concurrent state changes do not corrupt the JSON file
  - edge case: orphan workspace dirs in app/workspaces/ beyond GC_MAX_AGE are cleaned up

## Unit 5: Fix SDK parse_event crash on non-dict json.loads result
**Files:** `app/server/session_sdk.py`
**Test scenarios:**
  - happy path: parse_event correctly processes dict events from SDK stream
  - edge case: parse_event receives a bare string from json.loads and skips gracefully without AttributeError
  - edge case: asyncio.wait_for timeout fires and raises TimeoutError instead of hanging indefinitely

## Unit 6: Verify and run pytest gate + py_compile smoke on all edited files
**Files:** `tests/test_auth.py`, `tests/test_sessions.py`, `tests/test_sdk_phase2.py`
**Test scenarios:**
  - happy path: python -m py_compile passes on all modified .py files
  - happy path: pytest tests/ -x -q exits 0 (excluding 3 pre-existing SDK failures)
  - edge case: no new test failures introduced by the targeted fixes
