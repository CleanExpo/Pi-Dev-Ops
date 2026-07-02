---
name: terminal-orchestrator
description: Safely manage long-running tmux-based dev workflows (build, test, watch, log tailing) on the local machine via a constrained command grammar. Use when an agent or operator wants to inspect tmux state, start a known profile, or run an allowlisted command inside a tracked session. NEVER use for production deploys, force-pushes, secret-exfiltrating commands, or anything matching the denylist. Read policy/ before executing.
---

# Terminal Orchestrator (Pi-Dev-Ops local)

## When to invoke

- An agent / operator asks "what's running in tmux?" → `tmux:list`, `tmux:status`
- Need to capture the last N lines from a pane → `tmux:tail`
- Need to bring up a known dev/test/jobs/logs profile → `tmux:start <profile>`
- Need to run an allowlisted command inside a tracked pane → `tmux:run`

## Hard rules (non-negotiable)

1. **Policy files are the source of truth.** Read `policy/denylist.txt`,
   `policy/allowlist.yaml`, `policy/secret_patterns.txt` before any decision.
2. **Validator gates every command.** The Python validator at
   `swarm/tmux_validator.validate_command()` is the only path. Never call
   `tmux send-keys` without a prior `ValidationResult(allowed=True)`.
3. **Pane targeting uses stable `pane_id` (`%N`).** Never address panes by
   `session:window.index`.
4. **Audit ledger is fail-closed.** If `.harness/audit/tmux-YYYY-MM-DD.jsonl`
   cannot be written (missing dir, fsync failure, append-only flag not set),
   the call MUST be refused before any state change.
5. **No production mutation.** Commands matching `policy/denylist.txt`
   production-mutation patterns are blocked at every autonomy level, including
   under explicit operator confirmation.

## Autonomy levels

| Level | Capability |
|---|---|
| L1 | Read-only: `tmux:list`, `tmux:status`, `tmux:tail` |
| L2 | Preview-first run/start of allowlisted profiles + commands |
| L3 | Explicit per-call operator confirmation for `tmux:stop` or commands not on L2 allowlist |

## Validator usage

```python
from swarm.tmux_validator import validate_command, redact_secrets

result = validate_command("pytest -x swarm/intake/")
if not result.allowed:
    # surface result.reason, result.denylist_match to caller
    return result.to_dict()
# only now safe to invoke tmux send-keys
```

## Implementation status

- **T1 (observer)** — not yet implemented (next phase, will land separately)
- **T2 (safe runner)** — gated on T1
- **T3 (self-healing)** — gated on T2 + autonomy-ledger
- **T4 (approval-ledger integration)** — gated on T3

## Provenance

This skill ships only the policy + validator. T1-T4 implementations land in
follow-up PRs gated on operator approval. See `2nd-brain/Sketches/02-tmux-agent.md`
for the fat-marker sketch and grill transcript.


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
