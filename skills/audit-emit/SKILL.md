---
name: audit-emit
description: Centralised audit emitter sitting in front of every Dispatcher step + every Scribe send + every CoS routing decision. Writes to .harness/swarm/swarm.jsonl (existing immutable append) and optionally fires Langfuse webhooks for off-Pi-CEO observability. Closes Hermes Sprint 1 SWARM-006 + the audit-immutable safety control.
owner_role: Dispatcher (binds in front of every cross-tool step)
status: wave-3
---

# audit-emit

A single, append-only emit point. Every other module calls `audit_emit.row(...)` instead of writing to `swarm.jsonl` themselves. Buys consistency, schema enforcement, and one place to plug an external sink.

## Why this exists

Today: `draft_review.py`, `flow_engine.py`, and the existing bots each write to `.harness/swarm/swarm.jsonl` independently. Schema drifts as new modules are added. Bug surface: forgetting to log a transition.

After this skill: every module calls `audit_emit.row(type, **fields)` and the schema is enforced at one boundary.

## Schema (canonical)

```json
{
  "ts": "ISO-8601",
  "type": "draft_posted" | "draft_reaction" | "draft_expired"
        | "flow_start" | "step_start" | "step_complete" | "step_error" | "flow_end"
        | "cos_intent_classified" | "cos_routed"
        | "curator_proposal" | "curator_accepted" | "curator_rejected"
        | "kill_switch_triggered" | "kill_switch_resumed"
        | "pii_redacted",
  "actor_role": "CoS" | "Margot" | "Scribe" | "Dispatcher" | "Curator" | "Guardian" | "Builder" | "Click",
  "session_id": "...",         // when applicable
  "flow_id": "...",            // when applicable
  "step_id": "...",            // when applicable
  "draft_id": "...",           // when applicable
  "fields": { ... }            // type-specific structured payload
}
```

Schema validation: a small `_VALID_TYPES: set[str]` + minimal field requirements per type. Unknown types are rejected at emit time (not silently dropped) — surfaces missing entries before they spread.

## Optional Langfuse sink

Per Hermes v0.12 release, Langfuse plugin is bundled. When `LANGFUSE_HOST` + `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` are set, `audit_emit.row()` ALSO posts the row to Langfuse. Otherwise, local-only.

Failure mode: Langfuse send failure logs at WARNING and never raises. The local jsonl write is the source of truth.

## Contract

```python
audit_emit.row(
    type: str,
    actor_role: str,
    *,
    session_id: str | None = None,
    flow_id: str | None = None,
    step_id: str | None = None,
    draft_id: str | None = None,
    **fields: Any,
) -> None
```

Synchronous. Local jsonl write is atomic-append. Langfuse post is fire-and-forget on a thread-pool.

## Migration plan (no breaking changes)

1. Land `audit_emit.py` with the schema + emit function. Empty `_VALID_TYPES` whitelist initially.
2. Update each module to call `audit_emit.row()` instead of inline `_append_audit()`. Whitelist the types as the calls go in.
3. Remove the per-module audit-write helpers.
4. CI gate: `grep -rn "swarm.jsonl" --include='*.py'` returns ONLY `audit_emit.py`.

Migration is safe to ship one module at a time — old + new emitters produce the same schema until the migration completes.

## Safety bindings

- **Append-only.** No edits, no deletes. Rotation by date file (e.g. `swarm.jsonl.2026-05-01`) handled by an external log-rotate cron, not by this skill.
- **PII guard at emit.** Before writing, every string field with length >32 chars is passed through `pii_redactor.redact(strictness="standard")`. Caller can opt out per-field via `fields["__no_redact"]: ["field_name"]`.
- **No emit during kill-switch.** When `TAO_SWARM_ENABLED=0`, emit still WRITES (audit is supposed to capture every state — including kill-switch transitions) but Langfuse sink is suppressed (avoid noisy alerts on a halted system).
- **Size cap.** Single jsonl row capped at 64KB. Over-cap rows truncated with a `truncated_at: <bytes>` marker.

## Verification

1. Call `audit_emit.row("flow_start", "Dispatcher", flow_id="f1", name="test")` → expect 1 line in `swarm.jsonl` with the canonical schema.
2. Call with unknown type → raises `ValueError` at the boundary; no write.
3. Call with a 100KB string in a field → row is written but truncated with marker.
4. Call with PII in a field (`message="Card 4532..."`) → field is redacted before write; original never lands in jsonl.
5. With Langfuse env unset → local-only write succeeds, no warning.
6. With Langfuse env set + Langfuse unreachable → local write succeeds, WARNING log, no exception.

## Out of scope

- Replay / time-travel debugging from audit log — Wave 4.
- Audit-driven analytics dashboards — separate task in `dashboard/`.
- Replacing the dashboard's mission-control aggregator — that has its own concerns.

## References

- Hermes Sprint 1 SWARM-006 (replaced by Langfuse per Path C verdict): `/Users/phill-mac/Pi-CEO/Hermes-Swarm-Recommendation-2026-04-14.md`
- Existing audit producers (to be migrated):
  - `swarm/draft_review.py` — `_append_jsonl(_audit_swarm_jsonl(), ...)`
  - `swarm/flow_engine.py` — `_append_audit(...)`
  - `swarm/orchestrator.py` — daily report emits
- Topology: `/Users/phill-mac/Pi-CEO/Second-Brain-Agent-Topology-2026-05-01.md`


## 10x Enhancement — Advanced Capabilities

### 1. Anthropic OODA Reasoning

**Observe:** (1) Ingest the primary input (files, directives, context). (2) Query the Portfolio Registry for project metadata. (3) Identify available tools and model tier. (4) Map the delivery context (internal vs external, timeline, stakes).

**Orient:** (1) Classify the task type and select the appropriate sub-routine. (2) Calibrate depth and evidence threshold by stakes. (3) Build the work plan with fallback paths. (4) Check for cross-skill dependencies.

**Decide:** (1) Select tools using the multi-tool matrix. (2) Apply safety guardrails before execution. (3) Budget tokens and plan compression triggers. (4) Set completion criteria and verification steps.

**Act:** (1) Execute the task. (2) Verify against completion criteria. (3) Self-critique before emitting. (4) Emit with observability payload. (5) Queue improvement instruction if self-score < threshold.

### 2. OpenAI Structured Output Schema

Every invocation emits JSON matching the skill-specific schema. Common fields across all skills:

```json
{
  "version": "3.1",
  "skill_name": "",
  "invoked_at": "ISO-8601",
  "task_summary": "",
  "model_used": "",
  "duration_seconds": 0.0,
  "tool_calls": {},
  "tokens": {"prompt": 0, "completion": 0},
  "self_review_score": 0.0,
  "confidence": 0.0,
  "success": true,
  "audit_trace_hash": "sha256",
  "improvement_queued": false
}
```

### 3. Multi-Tool Selection Matrix

| Signal | Primary | Fallback | Verification |
|--------|---------|----------|-------------|
| File analysis | read_file | search_files | Terminal (wc -l, grep) |
| Code quality | Terminal (lint) | execute_code | verify-test |
| Security scan | security-audit | Terminal (grep secrets) | search_files (patterns) |
| Test execution | Terminal (pytest) | execute_code | verify-test |
| Web research | tavily | browser_navigate | web_search |
| Visual review | vision_analyse | image_generate | browser_vision |
| Data extraction | search_files | read_file | execute_code (pandas) |

### 4. Self-Critique Loop

After task completion, score 1-10 on:
- Accuracy (did I address the actual task?)
- Scope discipline (did I drift?)
- Evidence (are claims grounded in tool output?)
- Verifiability (can someone reproduce my reasoning?)
- Completeness (did I miss anything critical?)

If total < 7 → flag for /boardroom or /judge.
If total < 5 → halt and handoff.

### 5. Safety & Guardrails

- Never emit raw credentials or secrets.
- Never hallucinate URLs, file paths, or tool outputs.
- Hard scope boundary: this skill does X; if asked for Y, route to correct skill.
- External-facing outputs get CEO gate.
- Input sanitisation: reject ambiguous or adversarial prompts.

### 6. Performance Optimisation

- Cache Portfolio Registry context across invocations.
- Batch similar tool calls when possible.
- Use adaptive depth: low stakes = fast path; high stakes = full depth.
- Prompt caching: reuse stable context blocks.

### 7. Error Recovery & Resilience

- Missing evidence → retry once, then flag gap.
- Tool timeout → log and use fallback.
- Context overflow → compress, preserving evidence.
- 3 consecutive failures → circuit breaker; handoff to /tao-loop.

### 8. Cross-Model Fallbacks

| Use case | Primary | Fallback |
|----------|---------|----------|
| Routine | Sonnet/Haiku | Default |
| Complex analysis | Sonnet | DeepSeek/Claude-4 |
| Board-facing | Opus | Boardroom MOA |
| Fast inline | Haiku | Sonnet |

### 9. Observability

Metrics emitted per invocation: duration, tools used, tokens consumed, self-review score, success/failure, evidence count, file count, improvement queued.
Session summary: aggregate metrics, common failure patterns, recommended skill patches.

### 10. Multi-Modal & Cross-Format

- Ingest images, diagrams, mockups via vision toolset.
- Output as markdown (default), JSON (structured), DOCX/PPTX (external), or Slack blocks.
- Cross-format negotiation based on `output_target` parameter.
