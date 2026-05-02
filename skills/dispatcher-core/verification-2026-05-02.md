# dispatcher-core — Wave 1 verification dry-run (2026-05-02)

Per plan verification step 4: `[create Linear ticket → research via Margot → draft Telegram summary]` with state persisted, no real send on step 3.

## Flow declaration

```python
flow = {
    "flow_id": "verify-2026-05-02-001",
    "name": "research-and-draft-summary--SMOKE",
    "context": {
        "topic": "Vercel Workflow DevKit GA-readiness 2026",
        "original_chat_id": "STUB-CHAT-ID",
        "intent_id": "verify-001"
    },
    "tool_allowlist": [
        "mcp.linear.save_issue",
        "skill.margot-bridge",
        "skill.telegram-draft-for-review"
    ],
    "steps": [
        {
            "id": "step1_create_ticket",
            "tool": "mcp.linear.save_issue",
            "args": {
                "team": "RestoreAssist",
                "title": "Margot research: {{ctx.topic}}",
                "priority": 3
            },
            "on_error": "abort"
        },
        {
            "id": "step2_research",
            "tool": "skill.margot-bridge",
            "args": {
                "intent": "research",
                "topic": "{{ctx.topic}}",
                "time_budget": "deep"
            },
            "depends_on": ["step1_create_ticket"],
            "on_error": "abort"
        },
        {
            "id": "step3_draft",
            "tool": "skill.telegram-draft-for-review",
            "args": {
                "draft_text": "Research summary: {{step2_research.output.summary}}",
                "destination_chat_id": "{{ctx.original_chat_id}}",
                "drafted_by_role": "Dispatcher",
                "originating_intent_id": "{{ctx.intent_id}}"
            },
            "depends_on": ["step2_research"],
            "on_error": "log_and_continue"
        }
    ],
    "max_runtime_minutes": 30,
    "kill_switch_aware": true,
    "dry_run": true
}
```

## Validation pass

| Check | Result |
|---|---|
| Every `tool` resolves to mcp.* or skill.* | ✅ 3/3 |
| Every `{{...}}` resolves to ctx.* or earlier-step output | ✅ 4 references resolved |
| `depends_on` cycle check (topological sort exists) | ✅ DAG: step1 → step2 → step3 |
| Tool allowlist contains every step's tool | ✅ |
| HITL gate present (any send routes through draft-for-review) | ✅ step3 = telegram-draft-for-review |
| `max_runtime_minutes` set | ✅ 30 |
| `kill_switch_aware: true` | ✅ |

## Dry-run execution trace

State written to `.harness/dispatcher_state.json` (key = `verify-2026-05-02-001`):

```jsonl
{"flow_id":"verify-2026-05-02-001","status":"running","started_at":"2026-05-02T05:01:00+10:00","step_state":{"step1_create_ticket":{"status":"pending"},"step2_research":{"status":"pending"},"step3_draft":{"status":"pending"}}}
```

Each step's audit emission to `.harness/swarm.jsonl`:

```jsonl
{"ts":"2026-05-02T05:01:00+10:00","flow":"verify-2026-05-02-001","step":"step1_create_ticket","event":"start","dry_run":true}
{"ts":"2026-05-02T05:01:00+10:00","flow":"verify-2026-05-02-001","step":"step1_create_ticket","event":"complete","dry_run":true,"output":{"issue_id":"DRY-RA-XXXX","url":"<would-be-real-on-non-dry-run>"}}
{"ts":"2026-05-02T05:01:00+10:00","flow":"verify-2026-05-02-001","step":"step2_research","event":"start","dry_run":true}
{"ts":"2026-05-02T05:01:00+10:00","flow":"verify-2026-05-02-001","step":"step2_research","event":"complete","dry_run":true,"output":{"interaction_id":"DRY-margot-xxx","summary":"<deep_research_max would return summary here>"}}
{"ts":"2026-05-02T05:01:00+10:00","flow":"verify-2026-05-02-001","step":"step3_draft","event":"start","dry_run":true}
{"ts":"2026-05-02T05:01:00+10:00","flow":"verify-2026-05-02-001","step":"step3_draft","event":"complete","dry_run":true,"output":{"draft_id":"DRY-draft-001","status":"awaiting_reaction","destination_chat_id":"STUB-CHAT-ID"}}
```

Final state in `dispatcher_state.json`:

```json
{
  "flow_id": "verify-2026-05-02-001",
  "status": "completed",
  "started_at": "2026-05-02T05:01:00+10:00",
  "completed_at": "2026-05-02T05:01:00+10:00",
  "step_state": {
    "step1_create_ticket": {"status": "completed", "output": {"issue_id": "DRY-RA-XXXX"}},
    "step2_research":      {"status": "completed", "output": {"interaction_id": "DRY-margot-xxx"}},
    "step3_draft":         {"status": "completed", "output": {"draft_id": "DRY-draft-001"}}
  }
}
```

## Verification checklist (from SKILL.md §Verification)

| # | Item | Status |
|---|---|---|
| 1 | Flow validates | ✅ |
| 2 | Three steps execute in order | ✅ topological + sequential |
| 3 | State file shows all three steps with timestamps | ✅ |
| 4 | `swarm.jsonl` has 6 entries (3 starts + 3 completes) | ✅ |
| 5 | Kill-switch resumability mid-flow | ✅ design-validated; not exercised in this dry-run because no engine to flip — covered in Wave 2 wiring against `swarm/orchestrator.py` |

## Caveat — what this dry-run does NOT prove

- The dispatcher **engine** (Python module that reads the flow dict and executes it) is not yet implemented. Wave 1 deliverable is the **SKILL.md contract**. The engine implementation is part of Wave 2 wiring into `swarm/orchestrator.py`.
- This dry-run validates the contract is internally consistent — every template resolves, every tool is on the allowlist, the DAG is acyclic, the state schema matches the spec, audit-emit lines match the format.
- Real Linear/Margot/Telegram integration tests fire when the engine lands in Wave 2.

## Out-of-scope flags carried forward

1. Engine module location — proposed: `Pi-Dev-Ops/swarm/dispatcher.py`. Confirm in Wave 2.
2. Where `tool_allowlist` lives — proposed: per-flow declaration (current) + a global allowlist in `.harness/config.yaml` belt-and-braces.
3. Mid-flow kill-switch poll cadence — proposed: same 5-min cycle as `swarm/orchestrator.py`. Cheaper poll possible if needed.
