# Implementation Plan

**Session:** 73b7c07e4e6b  
**Confidence:** 42%

**Risk notes:** Brief specifies URGENT hotfix but does not name the failing component, endpoint, or error class. Plan assumes the most likely production failure modes from CLAUDE.md: import chain breakage (TAO_USE_AGENT_SDK), SDK auth 401 from empty ANTHROPIC_API_KEY, /health silent-success masking LINEAR_API_KEY absence, or SSE surface drop. Actual root cause may be in a different route module or the Railway deploy config — units 1-2 are designed to be redirected once the real error log is read. Confidence raised slightly by closed-loop smoke-test in unit 3. Will lower scope if issue is isolated to a single file.

## Unit 1: Reproduce & diagnose — inspect recent deploy diff and error surface
**Files:** `app/server/main.py`, `app/server/app_factory.py`, `app/server/routes/health.py`, `railway.toml`, `Dockerfile`
**Test scenarios:**
  - happy path: GET /health returns 200 with autonomy_loop boolean and last_tick timestamp present
  - edge case: server starts without LINEAR_API_KEY — /health must still return 200 but surface linear_api_key: false
  - edge case: import chain app.server.main:app resolves without ImportError (TAO_USE_AGENT_SDK=1 set)

## Unit 2: Fix root cause in backend route or startup sequence
**Files:** `app/server/routes/sessions.py`, `app/server/routes/auth.py`, `app/server/routes/webhooks.py`, `app/server/app_factory.py`
**Test scenarios:**
  - happy path: POST /api/build returns session id and begins streaming without 500
  - edge case: ANTHROPIC_API_KEY set to empty string — server pops it so SDK falls back to CLI OAuth, no HTTP 401
  - edge case: webhook with pidev/ ref is silently dropped and returns 200 without spawning recursive session

## Unit 3: Smoke-test import gate and pytest quick-pass
**Files:** `tests/test_server.py`, `tests/test_auth.py`, `scripts/smoke_test.py`
**Test scenarios:**
  - happy path: python -c 'from app.server.main import app' exits 0
  - happy path: pytest tests/ -x -q completes with only the 3 pre-known sdk-phase2 failures
  - edge case: py_compile passes on every edited Python file with zero SyntaxError

## Unit 4: Fix dashboard TypeScript error if frontend surface is broken
**Files:** `dashboard/hooks/useSSE.ts`, `dashboard/lib/phases.ts`, `dashboard/app/build/page.tsx`
**Test scenarios:**
  - happy path: npx tsc --noEmit exits 0 with no type errors
  - edge case: SSE drop re-frames as 'reconnecting' not 'disconnected', session status polls /api/sessions as fallback
  - edge case: completed session renders green Complete banner with score, branch name, and Fix next CTA — not silent/blank

## Unit 5: Stage conventional commit with fix: prefix — no push
**Files:** `app/server/routes/sessions.py`, `app/server/app_factory.py`, `dashboard/hooks/useSSE.ts`

## Unit 6: Write PR body to sandbox markdown file
**Files:** `/tmp/pi-ceo-workspaces/hotfix-pr-body.md`
