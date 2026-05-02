---
name: dispatcher-core
description: Cross-tool workflow primitive. Executes a declared sequence of steps that chain Linear, Gmail, Calendar, Margot, Composio, or any registered MCP tool. State persisted to .harness/dispatcher_state.json so kill-switch + crashes don't lose progress.
owner_role: Dispatcher
status: wave-1
---

# dispatcher-core

The primitive. A flow is an ordered list of steps; each step calls one MCP tool (or one skill) with inputs derived from earlier steps' outputs. State is journalled per step so the flow is resumable.

The *declarative surface* (YAML/JSON syntax users author by hand) is Wave 2 (`cross-tool-flow`). Wave 1 ships the engine, callable via the Python API.

## Flow shape

```python
flow = {
    "flow_id": "auto-generated",
    "name": "research-and-draft-summary",
    "steps": [
        {
            "id": "step1_create_ticket",
            "tool": "mcp.linear.save_issue",
            "args": { "team": "RA", "title": "Margot research: {{topic}}" },
            "on_error": "abort"
        },
        {
            "id": "step2_research",
            "tool": "skill.margot-bridge",
            "args": { "intent": "research", "topic": "{{topic}}", "time_budget": "deep" },
            "depends_on": ["step1_create_ticket"],
            "on_error": "abort"
        },
        {
            "id": "step3_draft",
            "tool": "skill.telegram-draft-for-review",
            "args": {
                "draft_text": "{{step2_research.output.summary}}",
                "destination_chat_id": "{{ctx.original_chat_id}}",
                "drafted_by_role": "Dispatcher",
                "originating_intent_id": "{{ctx.intent_id}}"
            },
            "depends_on": ["step2_research"],
            "on_error": "log_and_continue"
        }
    ],
    "max_runtime_minutes": 30,
    "kill_switch_aware": true
}
```

## Execution model

1. **Validate flow.** Every `tool` resolves to either an `mcp.<server>.<tool>` reference or a `skill.<name>` reference. Every `{{...}}` template variable resolves to either `ctx.*` (initial context) or `<step_id>.output.*`.
2. **Persist initial state** to `.harness/dispatcher_state.json` keyed by `flow_id`.
3. **Execute steps in topological order** (respecting `depends_on`). Each step:
   - Reads inputs (resolves templates against accumulated state)
   - Calls the tool/skill
   - Writes output back to state
   - Appends to `.harness/swarm.jsonl` audit
4. **On error**, behaviour per step's `on_error`:
   - `abort` → halt flow, mark `status: failed`, leave partial state for inspection
   - `log_and_continue` → log the error, mark step `status: error`, proceed to next step
   - `retry_3x` → exponential backoff retry, then abort if still failing
5. **Kill-switch aware.** If `TAO_SWARM_ENABLED=0` is observed mid-flow, current step finishes (or is aborted on its own checkpoint), state persists, flow marked `status: paused`. Resume on re-enable.
6. **Timeout.** `max_runtime_minutes` exceeded → mark `status: timeout`, persist state.

## State file format (`.harness/dispatcher_state.json`)

JSONL, one entry per flow:
```json
{
  "flow_id": "...",
  "name": "...",
  "started_at": "ISO-8601",
  "status": "running" | "paused" | "completed" | "failed" | "timeout",
  "context": { ... },
  "step_state": {
    "step1_create_ticket": {
      "status": "completed",
      "started_at": "...",
      "completed_at": "...",
      "output": { "issue_id": "RA-1839" }
    },
    "step2_research": { "status": "running", "interaction_id": "..." },
    "step3_draft": { "status": "pending" }
  }
}
```

## Safety

- **HITL gate not bypassable.** Any step calling `skill.telegram-draft-for-review` (or future `skill.linear-comment-draft`, etc.) automatically routes through the review queue. Dispatcher does NOT have a "send directly" mode.
- **Tool allowlist per flow.** Each flow declares which MCP tools it may call. Dispatcher rejects any step whose tool is not on the allowlist. Defense-in-depth in addition to the global skill allowlist.
- **No unbounded recursion.** A step cannot trigger another flow in Wave 1. Sub-flows arrive in Wave 3 with explicit depth limits.
- **Audit immutable.** Every step start + end appends to `.harness/swarm.jsonl`. Never overwritten. (Same pattern as existing swarm orchestrator.)

## When NOT to use this skill

- Single-tool calls — use the tool directly. Dispatcher overhead is justified at ≥2 chained steps.
- Anything that *just* drafts without coordinating across tools — use `telegram-draft-for-review` standalone.
- Code-generation / build flows — use `ship-chain` and `tier-orchestrator`. Dispatcher is for cross-tool, not code.

## Verification (Wave 1)

Run the example flow in `--dry-run` mode (no real Linear ticket, no real Margot call, no real Telegram send):
1. Flow validates ✅
2. Three steps execute in order ✅
3. State file `.harness/dispatcher_state.json` shows all three steps with timestamps ✅
4. `swarm.jsonl` has 6 entries (3 starts + 3 completes) ✅
5. With `TAO_SWARM_ENABLED=0` mid-flow: status flips to `paused`; on re-enable, resumes from where it stopped ✅

## Out of scope

- Declarative YAML/JSON authoring surface — Wave 2 `cross-tool-flow`.
- Sub-flows / nested dispatch — Wave 3.
- Parallel branches inside one flow — currently topologically ordered but sequential. Parallel is Wave 3.
- Cron-triggered flows — Wave 2 (uses existing `app/server/cron_scheduler.py`).
- Webhook-triggered flows — Wave 2 (uses existing `app/server/routes/webhooks.py`).

## References

- Topology: `/Users/phill-mac/Pi-CEO/Second-Brain-Agent-Topology-2026-05-01.md`
- Patterns borrowed from: `parallel-delegate` (fan-out shape), `ship-chain` (gate enforcement), existing swarm orchestrator state machine
