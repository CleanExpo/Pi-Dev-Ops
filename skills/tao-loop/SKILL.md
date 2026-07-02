---
name: tao-loop
description: Judge-gated autonomous coding loop runner. Port of pi-until-done's `/goal ... Ralph` pattern with single-metric termination via `tao_judge.judge`. One worker step per iteration, optional judge call every N iters, three independent abort axes from `kill_switch.LoopCounter` (MAX_ITERS, MAX_COST, HARD_STOP).
owner_role: Tier-Orchestrator (drives generator + evaluator; both sonnet per RA-1099)
status: wave-1
linear: RA-1970
---

# tao-loop

Iterates a generator step + judge step until the judge says done or the kill-switch
fires. Returns a fully-populated LoopResult; never raises KillSwitchAbort to the
caller.

## When to trigger

- A user issues an autonomy-class brief that warrants more than one iteration.
- A higher-level orchestrator wants a budget-bounded, judge-gated worker loop
  rather than the wave-orchestrated path.

## Public API

```python
from app.server.tao_loop import run_until_done, LoopResult

result = await run_until_done(
    goal="implement X",
    workspace="/path/to/repo",
    max_iters=10,                # else honour TAO_MAX_ITERS
    max_cost_usd=1.50,           # else honour TAO_MAX_COST_USD
    judge_every_n_iters=2,       # cost-control knob
    timeout_per_iter_s=600,
    on_event=lambda evt: ...,    # streamed iter_complete payloads
)
# result.done; result.reason; result.iters; result.cost_usd;
# result.judge_history; result.final_state
```

## Autoresearch envelope

The judge's `score` ∈ [0, 1] is the single termination scalar. The kill-switch
provides the orthogonal cost / iteration / hard-stop bounds.

## Kill-switch dependency

RA-1966's `LoopCounter` is constructed once per loop. `tick()` advances iters
and adds cost atomically, raising `KillSwitchAbort` on any breach — captured
into `LoopResult.reason`.

## CLI

`python scripts/run_tao_loop.py --goal "..." --workspace /path --max-iters N --max-cost X --judge-every N`


## 10x Enhancement — Advanced Capabilities

### 1. Anthropic OODA Reasoning

**Observe:** (1) Read the mission scope. (2) Map /.checkpoint/ for state. (3) Ingest DIRECTIVES.md and SPEC.md constraints. (4) Identify available toolsets and model tier. (5) Build the context canvas — all working state lives here.

**Orient:** (1) Validate context completeness (DIRECTIVES, SPEC, constraints, evidence). (2) Judge gate is re-evaluated per ACT; if judge-score < threshold, pause and score again. (3) Apply weighted urgency ordering to sub-tasks. (4) Check token budget: if <20% remaining, compact incoming and trim outgoing.

**Decide:** (1) Per Step: Classic ACT → judge review → checkpoint. (2) Set the exit conditions (max loops, score threshold, must-pass checks). (3) Select tools with fallback chains. (4) Calibrate model tier for the sub-task complexity.

**Act:** (1) Execute sub-task. (2) Persistent checkpoint. (3) Structured judge review. (4) If loop continues → loop; else → trigger-gateway-type-review.

### 2. OpenAI Structured Output Schema

Every CHECKPOINT has the following JSON envelope:

```json
{
  "version": "3.1",
  "step_id": 7,
  "checkpoint_content": "base64 wrapped content",
  "token_budget": {"remaining": 0, "total": 8192, "budget_status": "SAFE | MODERATE | CRITICAL | FULL"},
  "context_tokens": {"incoming": 0, "outgoing": 0, "state": 0, "template": 0},
  "tokens_threshold": 8192,
  "judge_review": {"should_continue": true, "score": 0.0, "threshold": 0.65, "risk_comment": ""},
  "action_list": [{"tool": "tavily", "purpose": "depth_iteration", "fallback": "search_files"}],
  "tool_chain": [{"step": 1, "tool": "tavily", "outcome": "SUMMARY | DEAD_END | TRAIL", "evidence": ""}],
  "merged_corpus": [],
  "output_format": "REPORT | CODE_FILE | MULTIMEDIA",
  "structured_parse_mode": "strict | output_tokens_as_time_params",
  "meta_structure": { "use_refs": false, "quotes_mode": "INLINE", "repeat_evidence": 100, "break_line_point": "---", "h_section_tracking": true },
  "final_outcome": { "verdict": "", "confidence": 0.0, "evidence_count": 0 }
}
```

### 3. Multi-Tool Selection Matrix

| Sub-task type | Primary tool | Fallback | Verification |
|---------------|-------------|----------|------------|
| Research/depth iteration | tavily | Search_files/Browse | Cross-reference |
| Code execution | Terminal | Execute_code | Type-check / lint |
| File operations (move/delete) | Terminal | Bash | diff verification |
| Data extraction | Search_files | read_file | Multiple source validation |
| Visual analysis | vision_analyse | browser_screenshot | OCR |
| Security scan | Security_audit | custom_script | Manual review trigger |

### 4. Self-Critique Loop

After every judge review:
- Did the ACT address the full task or just a safe subset? (coverage check)
- Is the output verifiable? (repeat_evidence + evidence_refs?)
- Did I stay within the DIRECTIVES and SPEC? (alignment check)
- Is the context token budget healthy? (budget check)
- Self-score per dimension: coverage (0.25), verifiability (0.25), alignment (0.25), budget health (0.15), tool selection (0.10). Total < 7 → pause and reassess.

### 5. Safety & Guardrails

- Resilience-restart rule: NEVER TAMPER WITH EXISTING FILES WITHOUT PRIOR CONSENT and CRITICAL context preservation. 
- Overlay new insights atop preserved originals. 
- No trolling, no side-stepping constraints, no force-override of judge.
- Any tool exceeding budget or alignment score goes into token-compaction mode for next iteration.
- Strict discipline: never use outputs for training. Respect confidentiality per Anthropic's ‘Responsible Scaling Policy.’

### 6. Performance Optimisation

- Context canvas: accumulate evidence as structured JSON to avoid re-reading.
- Token budget monitoring: check before every ACT; compact when MODERATE or above.
- Tool chain caching: if a previous tavily call for a query succeeded, reuse the result rather than re-executing.
- Batch judge reviews every N steps to reduce overhead.

### 7. Error Recovery & Resilience

- Pause conditions: judge-score ≤ 0.50; potential leak; significant anomaly; budget deficit (≤10% tokens).
- Context preservation rules: compress using context-compaction algorithm, not deletion.
- Escalation path: anomaly score ≥ 0.40 → escalate to /boardroom for override.
- Token overflow: enter token-compaction mode; trim internal-reserve first, then last-ACT evidence.

### 8. Cross-Model Fallbacks

| Complexity | Primary model | Fallback |
|------------|-------------|----------|
| Routine (>3 loops, score >0.8) | Default (Sonnet/Kimi) | Haiku for speed |
| Complex (deep analysis, <20K tokens) | Sonnet | DeepSeek equivalent |
| Critical (security, final audit) | Opus/Claude-4 | DeepSeek Reasoner |
| Emergency (judge override, divergence) | Boardroom MOA | Claude-Opus-4 |

### 9. Observability & Metrics

Emit after every loop:

```json
{"loop_id": 0, "timestamp": "", "step_id": 0, "model_tier": "", "tokens_used": {"prompt": 0, "completion": 0}, "judge_score": 0.0, "action": "ACT | REVIEW | PAUSE | STOP", "tool_used": "", "output_snippet": "", "is_terminal": false, "next_step_plan": ""}
```

Emit at mission end:

```json
{"mission_duration_seconds": 0, "total_loops": 0, "avg_judge_score": 0.0, "final_outcome": "", "final_verdict_confidence": 0.0, "total_tool_calls": 0, "unique_tools_used": [], "token_efficiency": 0.0, "anomalies_encountered": 0, "anomaly_handled": 0}
```

### 10. Multi-Modal & Cross-Format

- Ingest images/diagrams as context inputs (vision_analyse).
- When outputs include diagrams or videos, generate via the appropriate toolset (e.g., Remotion).
- Format negotiation: deliver as markdown, JSON, PPTX, DOCX, or Slack blocks depending on the target audience.
