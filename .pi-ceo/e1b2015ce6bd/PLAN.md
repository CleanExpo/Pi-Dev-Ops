# Implementation Plan

**Session:** e1b2015ce6bd  
**Confidence:** 38%

**Risk notes:** Brief states 'BUG — Bug Fix' but does not identify a specific bug. Plan targets the 4 highest-priority known bugs documented in CLAUDE.md hardwired lessons: (1) _req_log memory leak in auth.py, (2) ANTHROPIC_API_KEY empty-string env hygiene, (3) cron trigger last_fired_at reset on Railway redeploy causing missed windows, (4) parse_event non-dict crash in SDK stream. If the actual reported bug is different (e.g. a user-reported regression or a specific Linear/SSE issue), units 2-5 may be misaligned. session_sdk.py path assumed based on SDK Architecture table — verify file exists at app/server/session_sdk.py before editing. Confidence low due to ambiguity in bug identity.

## Unit 1: Diagnose: Identify active bug from logs, git history, and recent changes
**Files:** `app/server/routes/auth.py`, `app/server/routes/sessions.py`, `app/server/app_factory.py`, `app/server/session_sdk.py`

## Unit 2: Fix: Rate-limit GC — prune stale IPs from _req_log every 5 min inside check_rate_limit
**Files:** `app/server/routes/auth.py`
**Test scenarios:**
  - happy path: IPs with last request >120s ago are pruned on next check_rate_limit call
  - edge case: empty _req_log dict does not raise KeyError during prune
  - edge case: active IPs within 120s window are retained

## Unit 3: Fix: ANTHROPIC_API_KEY env hygiene — pop empty-string key before SDK invocation so subprocesses fall back to OAuth tokens
**Files:** `app/server/session_sdk.py`, `app/server/routes/sessions.py`
**Test scenarios:**
  - happy path: empty-string ANTHROPIC_API_KEY is removed from env before SDK call
  - edge case: None/unset key handled without AttributeError
  - edge case: valid non-empty key is preserved and passed through

## Unit 4: Fix: Cron trigger startup catch-up — fire overdue triggers within 10s of boot instead of waiting full interval
**Files:** `app/server/routes/triggers.py`, `app/server/app_factory.py`
**Test scenarios:**
  - happy path: trigger whose last_fired_at is older than its window fires within 10s of startup
  - edge case: trigger not yet due is not fired early
  - edge case: abs() used in debounce so negative timedelta from git-committed defaults does not skip

## Unit 5: Fix: parse_event guard — isinstance check after json.loads prevents crash on non-dict events in SDK stream
**Files:** `app/server/session_sdk.py`
**Test scenarios:**
  - happy path: dict event is parsed and fields extracted correctly
  - edge case: json.loads returning a string does not crash the phase loop
  - edge case: json.loads returning a list is skipped without exception

## Unit 6: Verify: Run pytest suite and tsc typecheck to confirm fixes and no regressions
**Files:** `tests/`, `dashboard/`
**Test scenarios:**
  - happy path: all tests pass except 3 pre-existing failures in test_sdk_phase2.py
  - edge case: npx tsc --noEmit exits 0 with no new type errors
