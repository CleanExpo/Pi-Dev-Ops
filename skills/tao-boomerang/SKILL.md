---
name: tao-boomerang
description: Token-efficient one-shot dispatch with summary-only return. Caller asks a question, the worker replies with ONLY the answer — no preamble, no chain-of-thought, no markdown unless the answer requires it. Composes on `_run_claude_via_sdk`. Use when you need the answer, not the conversation.
owner_role: foundational primitive — no agent boundary
status: wave-2
linear: RA-1994
---

# tao-boomerang

The "I just need the answer" pattern. Wraps `_run_claude_via_sdk` with
a summary-only preamble + post-strip of conversational artefacts.

## Public API

```python
from app.server.tao_boomerang import boomerang, dispatch_one

# Single
result = await dispatch_one(
    question="What's the latest stable Python version?",
    timeout_s=120,
)
# result.summary, result.cost_usd, result.elapsed_s, result.error

# Parallel
batch = await boomerang(
    questions=["q1", "q2", "q3"],
    max_parallel=5,
    timeout_s=120,
)
# batch.results, batch.total_cost_usd, batch.all_succeeded
```

`UNKNOWN: <reason>` is a contract — the worker returns this when the
question can't be answered without more context. Callers can branch
on `result.is_unknown`.

## When to trigger

- Research subagent calls where the caller throws away the
  reasoning trace anyway.
- Fact lookups that don't benefit from chain-of-thought (e.g.
  "current X price", "latest version of Y").
- Parallel batch queries where the per-result summary is what
  feeds the next stage.

## When NOT to use

- Anything that needs reasoning visible to the caller — use
  `_run_claude_via_sdk` directly with default thinking mode.
- Iterative goal pursuit — use `tao-loop` for that.
- Tool-heavy workflows (file edits, web fetch, etc.) — boomerang
  disables extended thinking and discourages tool use to keep
  output tight.

## Autoresearch envelope

| Slot | Value |
| --- | --- |
| Single metric | tokens-returned vs tokens-if-conversational |
| Time budget | per-call timeout, default 120s |
| Constrained scope | `app/server/tao_boomerang.py` |
| Strategy/tactic split | caller frames question; module enforces summary-only |
| Kill-switch | inherits SDK timeout + asyncio.wait_for wrapper |

## CLI

```bash
python scripts/run_boomerang.py "Your question"
python scripts/run_boomerang.py "q1" "q2" "q3" --max-parallel 3
python scripts/run_boomerang.py --json "What is X?"
```

## Composition

- **vs parallel-delegate (Agent tool):** boomerang is leaner. Agent
  tool returns the full subagent transcript. Boomerang strips to
  one paragraph max. Use Agent for "explore + report"; use
  boomerang for "answer this one thing".
- **vs tao-loop:** loop is iterative + judge-gated. Boomerang is
  one-shot. Don't compose them — if you need a goal-pursuit loop,
  go straight to tao-loop.
- **vs Margot deep_research:** Margot does multi-source synthesis
  with citations. Boomerang is a single SDK call. Use Margot when
  the answer needs grounding in the corpus or web.

## Behaviour invariants

- Worker model: Sonnet (`select_model("generator")`). Never opus.
- `thinking="disabled"` per dispatch — no extended thinking budget.
- Summary is post-stripped: leading "Sure, " / "Here is the answer: ",
  trailing "Let me know if..." footers, single-block markdown fences.
  Conservative: only strips when the WHOLE response matches a
  pattern, never edits the answer body.
- `error` populated on timeout / SDK error; `result.summary` empty
  in that case. Callers MUST check `error` before consuming summary.
