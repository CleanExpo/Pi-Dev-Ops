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
