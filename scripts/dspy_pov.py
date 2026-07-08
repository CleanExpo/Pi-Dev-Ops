#!/usr/bin/env python3
"""DSPy proof-of-value for the feedback_loop classifier (llm-stack-adoption item 4).

Compares, on the SAME held-out dev split and the SAME cheap-tier model:
  1. baseline  — the live `_classify_with_claude` prompt (the 0.944 full-set classifier)
  2. dspy-zero — an uncompiled dspy.Predict over an equivalent signature
  3. dspy-bfs  — the same module compiled with BootstrapFewShot on the train split

dspy is deliberately NOT a repo dependency (PoV per ADR-006 discipline). Run with:

    export OPENROUTER_API_KEY=...           # cheap tier, OFF Anthropic
    export TAO_MAX_ITERS=400                # compile makes >25 metric/LLM calls
    uv run --with dspy python scripts/dspy_pov.py

Cost guard: a kill_switch.LoopCounter ticks on every dev-eval and compile-metric
call with the measured per-call cost when dspy exposes it (LiteLLM), else a
conservative estimate — TAO_MAX_COST_USD (default $5) aborts the run hard.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.server import kill_switch  # noqa: E402
from app.server.agents import feedback_eval as fe  # noqa: E402

DATASET = "docs/experiments/2026-07-01-feedback-loop-eval/dataset.jsonl"
RESULT_JSON = "docs/experiments/2026-07-01-feedback-loop-eval/dspy_result.json"
MODEL = "openrouter/google/gemma-4-26b-a4b-it"  # same model as the baseline run
FALLBACK_COST_USD = 0.0005  # conservative; measured baseline ≈ $0.000025/call
HOLDOUT_PER_CLASS = 4  # 36 cases → 24 train / 12 dev


def _thread_of(case: fe.EvalCase) -> str:
    """Mirror _classify_with_claude's thread construction exactly."""
    thread = "\n---\n".join(case.comments[:30]) if case.comments else "(no comments)"
    thread = thread[:4000]
    return f"{thread}\n\nLinear state: {case.state}"


def _eval_baseline(dev: list[fe.EvalCase]) -> fe.EvalResult:
    from app.server.agents.feedback_loop import _classify_with_claude  # noqa: PLC0415

    return fe.run_eval(dev, _classify_with_claude)


def main() -> int:
    import dspy  # noqa: PLC0415  (only available under --with dspy)

    if not os.environ.get("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY not set — cheap tier unreachable", file=sys.stderr)
        return 1

    counter = kill_switch.LoopCounter()
    lm = dspy.LM(MODEL, max_tokens=300, temperature=0.0)
    dspy.configure(lm=lm)

    def _tick() -> None:
        cost = None
        if lm.history:
            cost = lm.history[-1].get("cost")
        counter.tick(cost_delta_usd=float(cost) if cost else FALLBACK_COST_USD)

    class ShipOutcome(dspy.Signature):
        """Classify the post-ship outcome of a feature from its Linear thread."""

        days_since: int = dspy.InputField(desc="days since the feature shipped")
        thread: str = dspy.InputField(desc="Linear comments and final state")
        category: Literal["positive", "negative", "neutral"] = dspy.OutputField()

    def to_example(case: fe.EvalCase) -> dspy.Example:
        return dspy.Example(
            days_since=case.days_since,
            thread=_thread_of(case),
            category=case.gold_category,
        ).with_inputs("days_since", "thread")

    def dspy_classify_fn(module):
        def classify(*, comments, state, days_since, pipeline_id):  # noqa: ARG001
            case = fe.EvalCase(pipeline_id, list(comments), state, days_since, "neutral")
            try:
                pred = module(days_since=days_since, thread=_thread_of(case))
            except kill_switch.KillSwitchAbort:
                raise
            except Exception:  # noqa: BLE001 — abstention, scored 0 like the baseline
                _tick()
                return None
            _tick()
            return {"category": pred.category}

        return classify

    def metric(example, pred, trace=None):  # noqa: ARG001
        _tick()
        return getattr(pred, "category", None) == example.category

    cases = fe.load_dataset(DATASET)
    train, dev = fe.stratified_split(cases, HOLDOUT_PER_CLASS)
    print(f"split: train={len(train)} dev={len(dev)} (holdout {HOLDOUT_PER_CLASS}/class)")

    results: dict[str, dict] = {}

    baseline = _eval_baseline(dev)
    results["baseline"] = {"accuracy": baseline.accuracy, "abstentions": baseline.abstentions}
    print(f"baseline   dev accuracy={baseline.accuracy:.3f} abstentions={baseline.abstentions}")

    zero = dspy.Predict(ShipOutcome)
    r = fe.run_eval(dev, dspy_classify_fn(zero))
    results["dspy-zero"] = {"accuracy": r.accuracy, "abstentions": r.abstentions}
    print(f"dspy-zero  dev accuracy={r.accuracy:.3f} abstentions={r.abstentions}")

    aborted = None
    try:
        optimizer = dspy.BootstrapFewShot(
            metric=metric, max_bootstrapped_demos=4, max_labeled_demos=4,
        )
        compiled = optimizer.compile(dspy.Predict(ShipOutcome), trainset=[to_example(c) for c in train])
        r = fe.run_eval(dev, dspy_classify_fn(compiled))
        results["dspy-bfs"] = {"accuracy": r.accuracy, "abstentions": r.abstentions}
        print(f"dspy-bfs   dev accuracy={r.accuracy:.3f} abstentions={r.abstentions}")
    except kill_switch.KillSwitchAbort as exc:
        aborted = {"reason": exc.args[0], "snapshot": counter.snapshot()}
        print(f"ABORTED by kill switch: {exc.args[0]} {counter.snapshot()}", file=sys.stderr)

    payload = {
        "model": MODEL,
        "split": {"train": len(train), "dev": len(dev)},
        "results": results,
        "kill_switch": counter.snapshot(),
        "aborted": aborted,
    }
    Path(RESULT_JSON).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {RESULT_JSON}  (llm calls ticked: {counter.iters}, est cost ${counter.cost_usd:.4f})")
    return 0 if aborted is None else 2


if __name__ == "__main__":
    raise SystemExit(main())
