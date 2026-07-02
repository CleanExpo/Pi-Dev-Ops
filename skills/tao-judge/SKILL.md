---
name: tao-judge
description: Single-scalar termination gate for the TAO judge-gated loop. Wraps a Sonnet evaluator call that scores a goal-state pair and returns a structured JudgeVerdict (done, reason, score 0..1, next_action_hint). The autoresearch principle — autonomy mandate gives intent, judge() gives a measurable termination condition.
owner_role: Tier-Worker (evaluator role; sonnet per RA-1099 model policy)
status: wave-1
linear: RA-1970
---

# tao-judge

JSON-only goal-completion evaluator. Called from `tao-loop` every N iterations
to decide whether the worker has met the goal.

## When to trigger

- A `tao-loop` iteration just finished a worker step and is at a judge-checkpoint.
- A higher-level orchestrator wants a one-shot scoring pass on the current
  goal-state pair without driving a full loop.

## Public API

```python
from app.server.tao_judge import judge, JudgeState, JudgeVerdict

verdict = await judge(
    goal="implement X",
    workspace="/path/to/repo",
    state=JudgeState(iters=3, last_test_output="...", last_diff="...", notes=[]),
    timeout_s=60,
    session_id="...",
)
# verdict.done bool; verdict.reason in {GOAL_MET, INSUFFICIENT_PROGRESS,
# TESTS_FAIL, TIMEOUT, STILL_WORKING}; verdict.score 0..1; verdict.next_action_hint
```

## Autoresearch envelope

`score` is the primary scalar. Higher = closer to GOAL_MET. The loop terminates
on `done=True` only when `reason="GOAL_MET"` — every other reason continues.

## Kill-switch dependency

Bubbles `KillSwitchAbort` from any caller in the SDK chain — never swallowed.
RA-1966 must be live (it is, on main).


## 10x Enhancement — Advanced Capabilities

### 1. Anthropic OODA Reasoning

**Observe:** (1) Identify the ACT step being reviewed. (2) Gather all evidence (DIRECTIVES, SPEC, tool outputs, previous judge scores). (3) Map the judging type (loop_gate, safety_expander, model_match, resource_audit, alignment_validator, final_scanner).

**Orient:** (1) Select the appropriate judging type. (2) Calibrate thresholds based on mission criticality. (3) Load the question-targets matrix. (4) Build a weighted rubric.

**Decide:** (1) Execute each question-target against evidence. (2) Turn unknown into risk + mitigations. (3) Compute the composite score. (4) Apply the strict gate logic.

**Act:** (1) Emit should_continue + score + risk_comment. (2) If reject: include the specific trigger question and remediation. (3) If accept: note any caveats / escalations. (4) Log the decision for audit.

### 2. OpenAI Structured Output Schema

Every judge review emits JSON:

```json
{
  "version": "3.1",
  "step_id": 0,
  "judge_type": "loop_gate | safety_expander | model_match | resource_audit | alignment_validator | final_scanner",
  "threshold": 0.65,
  "strict_mode": false,
  "evidence_used": [],
  "alignment_check": {"aligned": true, "directives_drift": [], "spec_violations": []},
  "should_continue": true,
  "score": 0.0,
  "risk_comment": "",
  "score_metadata": {
    "questions_targeted": ["", ""],
    "unknown_dealt_as_risk": true,
    "unknown_dealt_as_ignore": false,
    "composite_basis": "weighted_rubric",
    "weights": {"q1": 0.20, "q2": 0.20, "q3": 0.20, "q4": 0.20, "q5": 0.20}
  },
  "instruction_to_next_act_step": ""
}
```

### 3. Multi-Tool Selection Matrix

| Judge type | Evidence tools | Verification |
|---|---|---|
| loop_gate | read_file (DIRECTIVES, SPEC, ACT) | self_critique on alignment |
| safety_expander | security-audit (if available) | Resource audit tool |
| model_match | Terminal, read_file | Cross-reference with model output |
| resource_audit | Terminal (token count) | Token-compaction algorithm check |
| alignment_validator | read_file (DIRECTIVES), read_file (SPEC) | Comparison scan |
| final_scanner | read_file (all checkpoints) | Consistency summary |

### 4. Self-Critique Loop

After every review:
- Was the threshold appropriate for the mission criticality? Could it have been too lenient/strict?
- Did I flag all alignment violations? Check again.
- Did I score ambiguous evidence honestly (risk + mitigation) vs ignore it?
- If this were a tao-judge review of THIS review, would it pass?
- Score: rigor (0.3), fairness (0.3), alignment detection (0.3), escalation appropriateness (0.1). Total < 7 → flag for peer review.

### 5. Safety & Guardrails

- Judge never implements. It only reviews. If asked to code, route to tao-loop ACT.
- Strict mode: never allow should_continue unless unambiguous.
- Unknown evidence → risk + mitigation, never ignore.
- Honesty: if evidence is incomplete, lower score and require more evidence.

### 6. Performance Optimisation

- Cache DIRECTIVES and SPEC in state to avoid re-reading.
- Batch question-target checks when reviewing a multi-tool ACT.
- Reuse previous review patterns if the same step type recurs.
- Judge reviews can be batched every N steps (configurable, default N=3).

### 7. Error Recovery & Resilience

- Missing evidence → pause, request evidence from tao-loop.
- Contradictory evidence → escalate score threshold and require reconciliation.
- Token budget too low for full review → compact review (score only, detail in next loop).
- 3 consecutive high-side false positives (ACT should have passed but judge said no) → recalibrate threshold via /boardroom.

### 8. Cross-Model Fallbacks

| Use | Primary | Fallback |
|-----|---------|----------|
| Routine loop_gate | Sonnet/Haiku | Default |
| Safety-critical | Opus | DeepSeek Reasoner |
| Board-level audit | Opus | Boardroom |
| Fast inline check | Haiku | Sonnet |

### 9. Observability & Metrics

Emit per review: judge_type, threshold, strict_mode, should_continue, score, risk_comment, alignment_status, evidence_count.
Emit session summary: reviews_count, avg_score, avg_threshold, alignment_violations, false_positives, false_negatives, recalibration_events.

### 10. Multi-Modal & Cross-Format

- Review visual outputs (e.g., Remotion renders) via vision toolset.
- Judge output can be formatted as Slack blocks, JSON webhook, or markdown.
- Image-based evidence (screenshots, mockups) scored alongside text evidence.
