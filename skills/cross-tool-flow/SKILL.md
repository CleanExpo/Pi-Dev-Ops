---
name: cross-tool-flow
description: Declarative YAML/JSON authoring surface over dispatcher-core. Lets the user (or Margot, or Scribe) define multi-step cross-tool flows in plain text — chain Linear, Gmail, Calendar, Margot, Composio MCP tools — and run them via Dispatcher. Wave 2 surface; engine is dispatcher-core in Wave 1.
owner_role: Dispatcher
status: wave-2
---

# cross-tool-flow

The human-authored layer over `dispatcher-core`. A flow is a YAML or JSON file describing ordered steps, inputs from prior outputs, and error handling. Drop it in `Pi-Dev-Ops/flows/` or paste it in Telegram with the `/flow` command.

## Why this exists

`dispatcher-core` ships the engine — flows can be constructed in Python and executed. But authoring flows in Python every time defeats the purpose. This skill gives the user a declarative, source-controlled, reviewable format.

## Flow file format

**File location:** `Pi-Dev-Ops/flows/<flow-name>.yaml`. One flow per file.

**Schema (YAML):**

```yaml
flow:
  name: research-and-summarise
  description: Margot deep-researches a topic, drafts Telegram summary
  trigger: manual              # manual | telegram_command | cron | webhook
  trigger_config:
    command: /research          # only if trigger = telegram_command
    cron: "0 9 * * 1"           # only if trigger = cron
    webhook_path: ""            # only if trigger = webhook
  context_schema:
    - name: topic
      type: string
      required: true
    - name: time_budget
      type: enum[quick,deep]
      default: deep
  tool_allowlist:
    - skill.margot-bridge
    - skill.telegram-draft-for-review
  max_runtime_minutes: 30
  steps:
    - id: research
      tool: skill.margot-bridge
      args:
        intent: research
        topic: "{{ctx.topic}}"
        time_budget: "{{ctx.time_budget}}"
        use_corpus: true
      on_error: abort
    - id: draft
      tool: skill.telegram-draft-for-review
      args:
        draft_text: "{{research.output.summary}}"
        destination_chat_id: "{{ctx.original_chat_id}}"
        drafted_by_role: Dispatcher
        originating_intent_id: "{{ctx.intent_id}}"
      depends_on: [research]
      on_error: log_and_continue
```

**Schema (JSON):** identical structure, JSON syntax. YAML is preferred for human authoring; JSON is what the engine sees internally.

## Loader

`flow_loader.py` (new in Wave 2):
1. Discovers all YAML/JSON in `Pi-Dev-Ops/flows/`.
2. Validates schema (jsonschema).
3. Validates that every `tool` reference resolves and is on the flow's `tool_allowlist`.
4. Validates that every `{{...}}` template variable is satisfiable from `context_schema` or earlier step outputs.
5. Registers flows by trigger type:
   - `manual` → callable via API `POST /api/flows/{name}/run` with context body
   - `telegram_command` → CoS routes the command to Dispatcher
   - `cron` → registered with `app/server/cron_scheduler.py`
   - `webhook` → adds a route to `app/server/routes/webhooks.py`

## Templating

`{{ctx.X}}` — flow context (passed in at trigger time).
`{{<step_id>.output.X}}` — output from earlier step.
`{{env.X}}` — environment variable (read-only). Errors if unset; never silently empty.
`{{utc_now}}`, `{{date}}`, `{{user_tz}}` — built-ins.

**Defense-in-depth:** templates are NOT a Turing-complete language. No conditionals, no loops, no shell-out. If a flow needs branching, add a step that calls a skill with branching logic — keep flows declarative.

## Safety bindings (inherited from dispatcher-core)

- Tool allowlist enforced per-flow.
- HITL gate non-bypassable — any draft step routes through review chat.
- Kill-switch aware — flows pause on `TAO_SWARM_ENABLED=0`, resume on re-enable.
- Audit-immutable — every step's start/end appended to `.harness/swarm.jsonl`.
- **No flow can call another flow in Wave 2.** Sub-flow nesting is Wave 3 with explicit depth limits.
- **No flow can spawn a subprocess directly.** All execution goes through registered MCP tools or skills.

## Versioning

Flow files are checked into git. Convention: include a `version: N` field in the flow root; bump on schema-breaking changes. The loader keeps the latest version active; older versions accessible via `/api/flows/{name}/versions/{N}/run` for replay.

## Verification

1. Create `Pi-Dev-Ops/flows/test-research.yaml` with the example above.
2. Restart `flow_loader` → schema validates, flow registered.
3. Trigger via `POST /api/flows/test-research/run` with `{"topic": "Vercel Workflow DevKit", "time_budget": "quick"}` (dry-run flag).
4. State persists to `.harness/dispatcher_state.json` with two steps logged.
5. Schema-violating flow → loader rejects with line-numbered error message; flow not registered.
6. Tool not on allowlist → flow rejected at validation, not at runtime.

## Example flows to ship as starter set

| Flow file | Purpose |
|---|---|
| `flows/research-and-summarise.yaml` | Margot research + Telegram digest |
| `flows/file-and-research.yaml` | Linear ticket + Margot research linked + Telegram update |
| `flows/morning-briefing.yaml` | Replaces hardcoded `morning-briefing-7am` cron — now a flow |
| `flows/post-meeting-summary.yaml` | Triggered by calendar-watcher post-event hook |

## Out of scope for Wave 2

- Sub-flows / nesting — Wave 3.
- Parallel branches inside a flow (fan-out) — Wave 3.
- Conditional steps (`when: <expr>`) — Wave 3.
- Flow-to-flow event emission — Wave 3.
- A visual flow editor — never (out of scope for the project).

## References

- Engine spec: `Pi-Dev-Ops/skills/dispatcher-core/SKILL.md`
- Topology: `/Users/phill-mac/Pi-CEO/Second-Brain-Agent-Topology-2026-05-01.md`
- Existing cron scheduler: `Pi-Dev-Ops/app/server/cron_scheduler.py`
- Existing webhook router: `Pi-Dev-Ops/app/server/routes/webhooks.py`
