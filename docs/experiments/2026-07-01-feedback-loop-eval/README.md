# Experiment: feedback_loop classifier eval harness (2026-07-01)

**Status:** Harness + golden set shipped and unit-tested. **Baseline measured 2026-07-08**
— see "Baseline result" below.

## Why this exists

This is the **prerequisite** for two planned pieces of work that were both blocked
without it:

- **DSPy proof-of-value** (`llm-stack-adoption-decision` item 4) — a DSPy optimizer needs
  a labeled trainset and a metric to optimize against. Neither existed.
- **Langfuse eval PoV** (`ADR-006`) — the ADR mandates a golden eval dataset committed
  under `docs/experiments/`, scored against a baseline the tool must beat.

A recon of the classifier (2026-07-01) found **no labeled data anywhere** in the repo —
only 4 inline mock cases in `tests/test_sprinkle_feedback_loop.py`. This unit creates the
missing dataset and the measurement apparatus.

## What the classifier does

`app/server/agents/feedback_loop.py::_classify_with_claude` reads a shipped feature's
Linear thread (comments + state + age) and classifies the post-ship outcome as
`positive | negative | neutral`. It runs on the **cheap tier** (Ollama Gemma 4 ->
OpenRouter, deliberately OFF Anthropic per RA-2989); the `_with_claude` name is legacy.

## The metric — and why not `tao_judge`

**Metric = category agreement** (exact match on the three labels; overall = accuracy).

ADR-006 loosely referenced `tao_judge`'s scalar as the metric, but the recon showed that
is the wrong tool here: `tao_judge` scores **coding-goal completion** (a termination gate
for autonomous coding loops), not label correctness — a semantic mismatch. It is also
`async`, wrong-shaped for a `(example, prediction) -> float` metric, and runs on **paid
Anthropic Sonnet**, so every eval call would spend budget. Label-agreement is the correct,
free baseline — literally the ADR Contrarian's "50-line CSV harness" that any adopted tool
(DSPy or Langfuse) must beat.

## Files

- `dataset.jsonl` — 36 synthetic labeled cases (12 each: positive / negative / neutral),
  no PII. Neutral cases are deliberately ambiguous — that is the class the keyword
  classifier escalates to the LLM for, so it is where the LLM earns its keep.
- `app/server/agents/feedback_eval.py` — `load_dataset`, `category_agreement`, `run_eval`
  (provider-agnostic: takes a `classify_fn`).
- `scripts/eval_feedback_loop.py` — CLI that injects the live classifier and prints
  accuracy.
- `tests/test_feedback_eval.py` — unit tests for the metric, loader, and the golden set
  (needs no provider).

## Running the baseline

```bash
# needs Ollama running locally OR OPENROUTER_API_KEY set (cheap tier)
python scripts/eval_feedback_loop.py
```

Record the printed accuracy here as the **baseline** once run against the live tier. Any
DSPy-optimized prompt or Langfuse experiment is only worth adopting if it beats this
number on the same set (per ADR-006's "ship only on measured lift").

## Baseline result (measured 2026-07-08)

```
dataset=docs/experiments/2026-07-01-feedback-loop-eval/dataset.jsonl
n=36  accuracy=0.944  abstentions=0
  negative  n=12  acc=1.000
  neutral   n=12  acc=0.917
  positive  n=12  acc=0.917
```

- **Provider:** OpenRouter `google/gemma-4-26b-a4b-it` (cheap tier; Ollama not running,
  fell through to OpenRouter as designed). Total eval cost ≈ $0.001 for 36 calls.
- **Reading:** 34/36 correct; the two misses are one `neutral` and one `positive` case.
  This is the number DSPy or Langfuse must beat on the same set — at 94.4% there is
  little headroom, which strengthens the ADR-006 Contrarian's case that the plain
  CSV harness may be enough.

## DSPy PoV result (measured 2026-07-08)

```
split: train=24 dev=12 (holdout 4/class, deterministic — feedback_eval.stratified_split)
baseline   dev accuracy=0.917 abstentions=0   (live _PATTERN_PROMPT classifier)
dspy-zero  dev accuracy=0.917 abstentions=0   (uncompiled dspy.Predict, same signature)
dspy-bfs   dev accuracy=0.917 abstentions=0   (BootstrapFewShot, 4 demos from train)
```

- **Verdict: no lift.** All three tie at 11/12 on the identical dev split and identical
  model (`openrouter/google/gemma-4-26b-a4b-it`). DSPy compilation buys nothing here —
  the task is already near its ceiling with the plain prompt.
- **Cost/guardrails:** 28 LLM calls, ≈$0.0013; `kill_switch.LoopCounter` armed
  (`TAO_MAX_ITERS=400`, `TAO_MAX_COST_USD` default $5) and never tripped.
- **Runner:** `scripts/dspy_pov.py` (dspy is NOT a repo dependency — run via
  `uv run --with dspy python scripts/dspy_pov.py`). Raw numbers: `dspy_result.json`.
- **Implication for the 2026-07-15 ADR-006 review:** this is direct evidence for the
  Contrarian position — with a 0.944 full-set baseline and zero optimizer headroom,
  the in-repo CSV harness is sufficient; neither DSPy adoption nor a Langfuse
  experiment runner has a measured win to justify it on this workload.

## Next

1. ~~Run the baseline against the cheap tier; record the number in this README.~~ Done
   2026-07-08 (above).
2. ~~DSPy PoV.~~ Done 2026-07-08 (above) — no lift; do not adopt for this classifier.
3. Board: rule at the ADR-006 kill date (2026-07-15) with both numbers on the table.

Original DSPy plan (kept for provenance):
2. DSPy PoV: swap `_PATTERN_PROMPT` for a DSPy `Signature`/`Predict`, compile against a
   train split of this set using `category_agreement` as the metric, evaluate on a held-out
   split, compare to baseline. Keep compile OFF Opus; respect `TAO_MAX_COST_USD` by wiring a
   `kill_switch.LoopCounter` around the compile loop.
