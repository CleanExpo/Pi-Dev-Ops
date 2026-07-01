#!/usr/bin/env python3
"""Run the label-agreement baseline for the feedback_loop classifier.

Usage:
    python scripts/eval_feedback_loop.py [dataset.jsonl]

Runs the LIVE cheap-tier classifier (`feedback_loop._classify_with_claude`, which
routes to Ollama Gemma 4 -> OpenRouter, OFF Anthropic) over the golden set and
prints category-agreement accuracy. This produces the baseline number the DSPy
PoV (llm-stack-adoption-decision item 4) must beat.

Requires provider access (Ollama running locally, or OPENROUTER_API_KEY set).
The metric and dataset loading are unit-tested in tests/test_feedback_eval.py and
need no provider; only this live run does.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.server.agents import feedback_eval as fe  # noqa: E402

DEFAULT_DATASET = "docs/experiments/2026-07-01-feedback-loop-eval/dataset.jsonl"


def main(argv: list[str]) -> int:
    dataset = argv[1] if len(argv) > 1 else DEFAULT_DATASET
    cases = fe.load_dataset(dataset)

    # Imported here so the metric/dataset code stays importable without pulling
    # the provider stack (feedback_loop imports config, Linear, etc.).
    from app.server.agents.feedback_loop import _classify_with_claude

    result = fe.run_eval(cases, _classify_with_claude)
    print(f"dataset={dataset}")
    print(f"n={result.n}  accuracy={result.accuracy:.3f}  abstentions={result.abstentions}")
    for gold, bucket in sorted(result.per_category.items()):
        print(f"  {gold:8s}  n={int(bucket['n']):2d}  acc={bucket['accuracy']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
