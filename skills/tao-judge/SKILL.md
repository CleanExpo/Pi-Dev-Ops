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
