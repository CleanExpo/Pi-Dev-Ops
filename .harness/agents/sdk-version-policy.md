# claude_agent_sdk — Version Policy

_Created: 2026-04-11 (RA-577)_

---

## Current Version

```
claude-agent-sdk  (installed via pip in Railway Dockerfile)
```

Check the pinned version in `requirements.txt` (or `pyproject.toml` if migrated).

---

## Upgrade Policy

### Who owns upgrades

The Pi-Dev-Ops backend team (currently: Phill McGurk). One owner per bump, no silent auto-upgrades.

### Required before bumping

1. Read the SDK changelog — identify any breaking API changes to `ClaudeSDKClient`, `ClaudeAgentOptions`, `AssistantMessage`, `TextBlock`, `ResultMessage`.
2. Run the full smoke test suite against a local server with `TAO_USE_AGENT_SDK=1`:
   ```bash
   TAO_USE_AGENT_SDK=1 python scripts/smoke_test.py \
     --url http://127.0.0.1:7777 --password $TAO_PASSWORD
   ```
3. Verify `_run_prompt_via_sdk()` in `board_meeting.py` still works:
   ```bash
   TAO_USE_AGENT_SDK=1 python -c "
   from app.server.agents.board_meeting import _run_prompt_via_sdk
   result = _run_prompt_via_sdk('Say CONFIRMED.')
   assert 'CONFIRMED' in result.upper(), f'Got: {result!r}'
   print('PASS:', repr(result[:80]))
   "
   ```
4. Check `.harness/agent-sdk-metrics/` — p95 latency and success rate must not regress by more than 15%.
5. Update this file with the new version and date.

### API stability contract

These names must remain stable (breaking change = block the upgrade):

| Symbol | File | Why critical |
|--------|------|-------------|
| `ClaudeSDKClient` | sessions.py, board_meeting.py | Core client |
| `ClaudeAgentOptions` | sessions.py, board_meeting.py | Options constructor |
| `ClaudeSDKClient.connect()` | sessions.py | Lifecycle |
| `ClaudeSDKClient.query(prompt)` | sessions.py | Send prompt |
| `ClaudeSDKClient.receive_messages()` | sessions.py | Stream response |
| `ClaudeSDKClient.disconnect()` | sessions.py | Cleanup |
| `AssistantMessage` | sessions.py | Message type check |
| `ResultMessage` | sessions.py | Termination signal |
| `TextBlock` | sessions.py | Text extraction |

If any of the above changes, update `_run_claude_via_sdk()` in `sessions.py` and `_run_prompt_via_sdk()` in `board_meeting.py` before deploying.

---

## Rollback

If the SDK path causes production failures:

1. Set `TAO_USE_AGENT_SDK=0` in Railway env vars — takes effect on next request, no redeploy needed.
2. Investigate errors in `.harness/agent-sdk-metrics/` (check `error` field).
3. Fix or pin the previous SDK version in `requirements.txt`, then redeploy.

The subprocess fallback (`claude -p`) is always available at `TAO_USE_AGENT_SDK=0` until Phase 3 (RA-576) removes it.

---

## Phase Milestones

| Phase | Ticket | Description | Status |
|-------|--------|-------------|--------|
| 1 | RA-556 | `board_meeting.py` SDK PoC | ✅ Done |
| 2a | RA-571 | `sessions.py` generator SDK path | ✅ Done |
| 2b | RA-572 | `sessions.py` evaluator SDK path | ✅ Done |
| 2c | RA-573 | SDK metrics collection | ✅ Done |
| 2d | RA-577 | CLAUDE.md + config.yaml update | ✅ Done |
| 3 | RA-574 | Canary rollout plan (10%→50%→100%) | ⏳ Todo |
| 4 | RA-575 | Smoke-test SDK path | ⏳ Todo |
| 5 | RA-576 | Remove subprocess fallback | ⏳ Blocked on canary |
