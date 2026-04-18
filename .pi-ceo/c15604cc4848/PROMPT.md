# Task Brief

[URGENT] [Pi-CEO CRITICAL] MAX_CONCURRENT_SESSIONS is effectively disabled — checks nonexistent status "running"

Description:
## Bug

`app/server/sessions.py:127`:

```python
_running = sum(
    1 for s in _sessions.values()
    if (isinstance(s, BuildSession) and s.status == "running")
    or (isinstance(s, dict) and s.get("status") == "running")
)
if _running >= config.MAX_CONCURRENT_SESSIONS:
    raise RuntimeError("Max sessions reached")
```

**There is NO code path that sets** `session.status = "running"`. The real status transitions are:

* `cloning` (set in `session_phases.py:523, 533`)
* `building` (set in `session_phases.py:888, 1145` and `routes/sessions.py:140`)
* `complete` / `failed` / `killed` / `interrupted` (terminal)

So `_running` is always 0. `MAX_CONCURRENT_SESSIONS=3` limit **does nothing**. Pi-CEO can spawn unbounded sessions.

## Observed today (2026-04-18 04:57 UTC)

33 concurrent sessions in flight simultaneously post-orphan-recovery + autonomy resume. Should have been capped at 3. Resource exposure: 33× Claude generator tokens, 33× clone bandwidth, 33× Railway memory. A compromised or misbehaving poller could trivially exhaust Railway quotas.

## Same failure class as [RA-1294](https://linear.app/unite-group/issue/RA-1294/pi-ceo-docs-add-comprehensive-analysis-spec-for-skills-and-tao-engine)

One-field-reads-wrong-value bug, shipped past tests because the field's nonexistence wasn't caught at runtime — the check silently returns 0 instead of raising. [RA-1154](https://linear.app/unite-group/issue/RA-1154/process-smoke-test-coverage-gap-ci-green-new-feature-works) senior E2E (merged today) catches the SPAWN→PR path but doesn't validate concurrency caps.

## Fix

Change `"running"` to `"building"` (plus include `"cloning"` since that's the bootstrap state where we're ALSO burning resources):

```python
_running = sum(
    1 for s in _sessions.values()
    if (isinstance(s, BuildSession) and s.status in ("cloning", "building"))
    or (isinstance(s, dict) and s.get("status") in ("cloning", "building"))
)
```

## Acceptance

* Unit test: create 3 BuildSession objects with status="building", call `create_session` → raises RuntimeError.
* Same test with status="complete" on all 3 → new session spawns fine.
* Integration test: fire 5 consecutive /api/build calls within 1 s, assert at most 3 are in cloning+building state at any moment.

## Urgency

P1 — resource exposure + compounds Railway-restart blast radius (more sessions = more orphans per restart).

Linear ticket: RA-1375 — https://linear.app/unite-group/issue/RA-1375/pi-ceo-critical-max-concurrent-sessions-is-effectively-disabled-checks
Triggered automatically by Pi-CEO autonomous poller.


## Session: c15604cc4848
