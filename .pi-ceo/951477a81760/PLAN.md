# Implementation Plan

**Session:** 951477a81760  
**Confidence:** 37%

**Risk notes:** Brief supplies no ticket number or explicit feature description — plan assumes the five unimplemented technical-debt items explicitly prescribed in CLAUDE.md (rate-limit GC, workspace GC, autonomy do-while, health liveness state, cron catch-up). If the actual intent is a different feature these units should be replaced. Workspace GC logic may live in app_factory.py startup hook rather than sessions.py depending on where _sessions and workspaces are co-located. Cron trigger persistence path (app/data/cron-triggers.json vs DB) should be confirmed before implementing unit 5. Test file names follow the pytest layout already present in tests/.

## Unit 1: Rate-limit GC: prune stale IPs inside check_rate_limit()
**Files:** `app/server/routes/auth.py`, `tests/test_auth.py`
**Test scenarios:**
  - happy path: IPs with last-request timestamp >120s ago are removed from _req_log during check_rate_limit call
  - edge case: no stale IPs present — _req_log dict unchanged after prune
  - edge case: all IPs are recent — none pruned, counts unaffected
  - edge case: prune fires at most once per 5-min window, not on every request

## Unit 2: Workspace GC: delete terminal-state session dirs after GC_MAX_AGE and orphan sweep
**Files:** `app/server/routes/sessions.py`, `tests/test_sessions.py`
**Test scenarios:**
  - happy path: completed/failed/killed/interrupted workspace dirs older than GC_MAX_AGE (default 4h) are removed atomically
  - edge case: active or pending session workspace is never deleted
  - edge case: orphan dirs under app/workspaces/ not referenced in _sessions are also GC'd
  - edge case: GC_MAX_AGE env var (integer seconds) overrides the 4h default

## Unit 3: Autonomy do-while fix: 10s startup delay so first poll fires promptly
**Files:** `app/server/autonomy.py`, `tests/test_autonomy.py`
**Test scenarios:**
  - happy path: first poll executes within 10s of startup rather than waiting a full 5-min interval
  - edge case: missing LINEAR_API_KEY causes poll to be skipped and logged, not silently ignored
  - edge case: rapid restart does not double-fire if last poll occurred within current interval

## Unit 4: Health endpoint: surface loop liveness, last_tick_at, and linear_api_key presence
**Files:** `app/server/routes/health.py`, `tests/test_health.py`
**Test scenarios:**
  - happy path: /health returns loop_will_fire: true, last_tick_at: <ISO-8601>, linear_api_key: true when fully configured
  - edge case: LINEAR_API_KEY absent in env → response includes linear_api_key: false
  - edge case: autonomy loop has never completed a tick → last_tick_at is null, not omitted

## Unit 5: Cron trigger catch-up: fire overdue triggers within 10s of server boot
**Files:** `app/server/routes/triggers.py`, `tests/test_triggers.py`
**Test scenarios:**
  - happy path: trigger whose last_fired_at is older than its interval fires within 10s of boot
  - edge case: trigger fired within current window is correctly skipped on startup
  - edge case: abs() in debounce check prevents negative time-drift from blocking legitimate catch-up fires
