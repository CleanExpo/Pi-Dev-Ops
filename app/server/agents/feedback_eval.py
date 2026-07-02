"""Offline label-agreement eval harness for the feedback_loop classifier.

Prerequisite for the DSPy proof-of-value (llm-stack-adoption-decision item 4)
and the Langfuse eval PoV (ADR-006): a labeled golden set plus a baseline
metric the optimizer must beat.

**Metric = category agreement** (exact match on positive|negative|neutral) — NOT
`tao_judge`. `tao_judge` scores coding-goal completion (a semantic mismatch for
classification) and runs on paid Anthropic Sonnet; label-agreement is the correct,
free baseline (the ADR Contrarian's "50-line CSV harness").

The harness is provider-agnostic: `run_eval` takes a `classify_fn` with the same
signature as `feedback_loop._classify_with_claude`, so tests inject a fake and the
CLI (`scripts/eval_feedback_loop.py`) injects the live cheap-tier classifier.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

VALID_CATEGORIES = frozenset({"positive", "negative", "neutral"})


@dataclass(frozen=True)
class EvalCase:
    """One labeled example: classifier inputs + the gold category."""

    pipeline_id: str
    comments: list[str]
    state: str
    days_since: int
    gold_category: str


def load_dataset(path: str | Path) -> list[EvalCase]:
    """Load a JSONL golden set. Blank lines and `#` comment lines are skipped.

    Raises ValueError on an unknown gold_category so a malformed dataset fails
    loud rather than silently scoring against a bad label.
    """
    cases: list[EvalCase] = []
    for lineno, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        d = json.loads(line)
        gold = d["gold_category"]
        if gold not in VALID_CATEGORIES:
            raise ValueError(f"line {lineno}: bad gold_category {gold!r}")
        cases.append(
            EvalCase(
                pipeline_id=d.get("pipeline_id", f"case-{lineno}"),
                comments=list(d.get("comments", [])),
                state=d.get("state", ""),
                days_since=int(d.get("days_since", 0)),
                gold_category=gold,
            )
        )
    return cases


def category_agreement(gold: str, pred: str | None) -> float:
    """1.0 if the predicted category exactly matches gold, else 0.0.

    A None prediction (classifier abstained/failed) scores 0.0 — an abstention
    is not a correct answer for accuracy purposes.
    """
    return 1.0 if pred is not None and pred == gold else 0.0


# classify_fn(*, comments, state, days_since, pipeline_id) -> {"category": ...} | None
ClassifyFn = Callable[..., dict[str, Any] | None]


@dataclass
class EvalResult:
    n: int
    correct: float
    accuracy: float
    abstentions: int
    per_category: dict[str, dict[str, float]] = field(default_factory=dict)


def run_eval(cases: list[EvalCase], classify_fn: ClassifyFn) -> EvalResult:
    """Run `classify_fn` over every case and score category agreement.

    Returns overall accuracy, an abstention count (classifier returned None),
    and a per-gold-category breakdown.
    """
    correct = 0.0
    abstentions = 0
    per: dict[str, dict[str, float]] = {}
    for case in cases:
        out = classify_fn(
            comments=case.comments,
            state=case.state,
            days_since=case.days_since,
            pipeline_id=case.pipeline_id,
        )
        pred = out.get("category") if out else None
        if out is None:
            abstentions += 1
        score = category_agreement(case.gold_category, pred)
        correct += score
        bucket = per.setdefault(case.gold_category, {"n": 0.0, "correct": 0.0})
        bucket["n"] += 1
        bucket["correct"] += score
    n = len(cases)
    for bucket in per.values():
        bucket["accuracy"] = bucket["correct"] / bucket["n"] if bucket["n"] else 0.0
    return EvalResult(
        n=n,
        correct=correct,
        accuracy=correct / n if n else 0.0,
        abstentions=abstentions,
        per_category=per,
    )
