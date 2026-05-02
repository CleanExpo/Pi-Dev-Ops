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
