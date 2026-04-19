# Implementation Plan

**Session:** 233810a13433  
**Confidence:** 42%

**Risk notes:** Brief specifies 'BUG — Bug Fix' without naming the specific bug. Plan covers the four highest-probability bugs explicitly documented in CLAUDE.md hardwired lessons: (1) _req_log stale-IP GC in auth.py, (2) ANTHROPIC_API_KEY='' env poisoning, (3) parse_event bare-string crash, (4) webhook self-modification recursion. If the actual bug is different (e.g. a dashboard SSE drop, Supabase write failure, or model-policy bypass), the relevant unit is not covered and confidence drops further. Session 233810a13433 workspace CLAUDE.md was also read — no additional bug specifics found there. Confidence capped at 0.42 due to ambiguity.

## Unit 1: Investigate and reproduce the reported bug
**Files:** `app/server/routes/auth.py`, `app/server/routes/sessions.py`, `app/server/routes/webhooks.py`, `app/server/app_factory.py`, `app/server/routes/health.py`
**Test scenarios:**
  - happy path: identify exact failure condition from logs or known issue patterns
  - edge case: check rate-limit GC — _req_log keys accumulate forever without pruning stale IPs
  - edge case: ANTHROPIC_API_KEY='' inherited by subprocesses causes HTTP 401 in SDK invocations
  - edge case: parse_event receives a bare string from json.loads instead of dict, crashing .get() call

## Unit 2: Fix rate-limit GC stale-IP accumulation in auth.py
**Files:** `app/server/routes/auth.py`
**Test scenarios:**
  - happy path: stale IPs (last request >120s ago) are pruned inline inside check_rate_limit() every 5 min
  - edge case: pruning does not accidentally remove active IPs under load
  - edge case: in cloud mode, X-Forwarded-For is used as client IP key, not request.client.host

## Unit 3: Fix API key env hygiene — pop empty ANTHROPIC_API_KEY before SDK calls
**Files:** `app/server/routes/sessions.py`, `app/server/session_sdk.py`
**Test scenarios:**
  - happy path: os.environ.pop('ANTHROPIC_API_KEY', None) called when value is empty string before SDK invocation
  - edge case: non-empty API key is left intact and used correctly
  - edge case: subprocess claude invocations fall back to CLI OAuth tokens when key is absent

## Unit 4: Fix parse_event isinstance guard in SDK stream handler
**Files:** `app/server/routes/sessions.py`
**Test scenarios:**
  - happy path: json.loads result is checked with isinstance(evt, dict) before calling .get()
  - edge case: bare string from json.loads ('hello') is skipped gracefully without crashing the phase
  - edge case: valid dict events are processed correctly through the full parse path

## Unit 5: Fix webhook self-modification guard — skip pidev/ refs and Pi-Dev-Ops repo
**Files:** `app/server/routes/webhooks.py`
**Test scenarios:**
  - happy path: push events with refs containing 'pidev/' are skipped with no session created
  - edge case: push events from CleanExpo/Pi-Dev-Ops repo are skipped to prevent recursive self-modification
  - edge case: legitimate push events from other repos are still processed normally

## Unit 6: Run full test suite and verify no regressions
**Files:** `tests/`, `app/server/routes/auth.py`, `app/server/routes/sessions.py`, `app/server/routes/webhooks.py`
**Test scenarios:**
  - happy path: pytest tests/ -x -q passes with only the 3 pre-existing failures in test_sdk_phase2.py
  - happy path: python -c 'from app.server.main import app' imports cleanly
  - edge case: no new test failures introduced by any of the targeted fixes
