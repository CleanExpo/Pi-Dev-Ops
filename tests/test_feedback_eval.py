"""Tests for the feedback_loop label-agreement eval harness.

Prerequisite unit for the DSPy PoV (llm-stack item 4) and the Langfuse eval PoV
(ADR-006): a labeled golden set + a baseline metric the optimizer must beat.
Metric = category agreement (NOT tao_judge — that scores coding-goal completion,
a semantic mismatch, and runs on paid Anthropic Sonnet).
"""
from __future__ import annotations

import pathlib

import pytest

from app.server.agents import feedback_eval as fe


def test_category_agreement_exact_match():
    assert fe.category_agreement("positive", "positive") == 1.0
    assert fe.category_agreement("negative", "negative") == 1.0


def test_category_agreement_mismatch_and_none():
    assert fe.category_agreement("positive", "negative") == 0.0
    assert fe.category_agreement("neutral", None) == 0.0


def test_load_dataset_shape(tmp_path):
    p = tmp_path / "d.jsonl"
    p.write_text(
        '{"pipeline_id":"A","comments":["x"],"state":"Done","days_since":2,"gold_category":"positive"}\n'
        "# a comment line is skipped\n"
        "\n",
        encoding="utf-8",
    )
    cases = fe.load_dataset(p)
    assert len(cases) == 1
    assert cases[0].pipeline_id == "A"
    assert cases[0].gold_category == "positive"
    assert cases[0].comments == ["x"]


def test_load_dataset_rejects_bad_category(tmp_path):
    p = tmp_path / "d.jsonl"
    p.write_text('{"gold_category":"great"}\n', encoding="utf-8")
    with pytest.raises(ValueError):
        fe.load_dataset(p)


def test_run_eval_perfect_and_partial():
    cases = [
        fe.EvalCase("A", ["x"], "Done", 2, "positive"),
        fe.EvalCase("B", ["y"], "Done", 3, "negative"),
    ]

    def perfect(*, comments, state, days_since, pipeline_id):
        gold = {"A": "positive", "B": "negative"}[pipeline_id]
        return {"category": gold, "label": "", "confidence": 1.0}

    r = fe.run_eval(cases, perfect)
    assert r.accuracy == 1.0
    assert r.abstentions == 0
    assert r.per_category["positive"]["accuracy"] == 1.0

    def always_positive(*, comments, state, days_since, pipeline_id):
        return {"category": "positive", "label": "", "confidence": 1.0}

    r2 = fe.run_eval(cases, always_positive)
    assert r2.accuracy == 0.5


def test_run_eval_counts_abstentions():
    cases = [fe.EvalCase("A", ["x"], "Done", 2, "positive")]

    def abstain(*, comments, state, days_since, pipeline_id):
        return None

    r = fe.run_eval(cases, abstain)
    assert r.abstentions == 1
    assert r.accuracy == 0.0


def test_golden_dataset_loads_balanced_and_min_size():
    """Bind the shipped golden set to the harness: >=30 cases, all 3 categories."""
    root = pathlib.Path(__file__).resolve().parents[1]
    ds = root / "docs/experiments/2026-07-01-feedback-loop-eval/dataset.jsonl"
    cases = fe.load_dataset(ds)
    assert len(cases) >= 30
    assert {c.gold_category for c in cases} == {"positive", "negative", "neutral"}
    # every case has non-empty comments and a valid state
    assert all(c.comments and c.state for c in cases)
