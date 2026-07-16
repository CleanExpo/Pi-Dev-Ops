"""Tests for the promotion CLI's write path (scripts/review_eval_candidates.py).

Acceptance criteria covered (spec §15): #3 only the human-accept path writes to
the golden file; #4 what is written is the synthetic paraphrase, never the
captured thread_redacted text.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import review_eval_candidates as cli  # noqa: E402

_CANDIDATE = {
    "id": 7,
    "pipeline_id": "pipe-42",
    "thread_redacted": "client [NAME_1] confirmed the rollout after [EMAIL_1] sign-off",
    "state": "Done",
    "days_since": 6,
    "predicted_category": "positive",
    "captured_at": "2026-07-08T00:00:00+00:00",
    "status": "pending",
}


def test_golden_case_contains_paraphrase_never_source():
    case = cli.candidate_to_golden(_CANDIDATE, "shipped the rollout and the team confirmed it works", "positive")
    dumped = yaml.safe_dump(case)
    assert "shipped the rollout" in dumped
    assert "[NAME_1]" not in dumped and "[EMAIL_1]" not in dumped
    assert "thread_redacted" not in dumped
    assert case["expected"] == "positive"


def test_keyword_tier_requires_decidable_agreement():
    # decidable + agrees → keyword
    assert cli.keyword_tier("the deploy works and client happy", "positive") == "keyword"
    # decidable but DISAGREES with founder label → llm (never break blocking CI)
    assert cli.keyword_tier("the deploy works and client happy", "negative") == "llm"
    # undecidable (no keywords) → llm
    assert cli.keyword_tier("quiet thread, no strong signal either way", "neutral") == "llm"


def test_append_golden_case_roundtrip(tmp_path):
    golden = tmp_path / "feedback_loop.yaml"
    golden.write_text(yaml.safe_dump({"cases": []}))
    case = cli.candidate_to_golden(_CANDIDATE, "synthetic thread about a happy launch that works", "positive")
    cli.append_golden_case(golden, case)
    doc = yaml.safe_load(golden.read_text())
    assert len(doc["cases"]) == 1
    assert doc["cases"][0]["comments"] == ["synthetic thread about a happy launch that works"]


def test_reject_and_skip_write_nothing(tmp_path, monkeypatch):
    """Drive review() end-to-end with injected input: reject then skip —
    the golden file must remain untouched."""
    golden = tmp_path / "feedback_loop.yaml"
    golden.write_text(yaml.safe_dump({"cases": []}))
    monkeypatch.setattr(cli, "GOLDEN_PATH", golden)
    monkeypatch.setattr(cli, "judge_opinion", lambda c: "judge unavailable (test)")
    monkeypatch.setattr(cli, "draft_paraphrase", lambda c: None)

    queue = tmp_path / "candidates.jsonl"
    import json
    rows = [dict(_CANDIDATE, captured_at=f"2026-07-08T00:00:0{i}+00:00") for i in range(2)]
    queue.write_text("".join(json.dumps(r) + "\n" for r in rows))
    monkeypatch.setattr(cli, "LOCAL_QUEUE", queue)

    answers = iter(["r", "s"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    assert cli.review(local=True, limit=10) == 0

    assert yaml.safe_load(golden.read_text())["cases"] == []
    statuses = [json.loads(line)["status"] for line in queue.read_text().splitlines()]
    assert statuses == ["rejected", "pending"]
