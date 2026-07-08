"""Prove-It golden suite — feedback_loop outcome classifier (RA-7014 slice 4).

Spec: docs/specs/spec-cap5-slice4-online-eval.md. Cases are human-accepted
synthetic paraphrases promoted via scripts/review_eval_candidates.py.

keyword-tier cases assert the deterministic keyword classifier (_detect_signal
short-circuits before any LLM call when a positive/negative keyword is present),
so this suite is CI-safe with no provider keys. llm-tier cases (future) are
schema-validated only.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

# NOTE: app.server.agents.feedback_loop is imported INSIDE the tests, not here.
# Importing it pulls in app.server.config, which loads .env.local into
# os.environ at pytest COLLECTION time — flipping test_intent_judge's
# module-level ANTHROPIC_API_KEY skip condition and un-skipping the live judge
# against whatever key happens to be on disk. Function-level import runs after
# all module imports, so collection stays side-effect free.

_GOLDEN = Path(__file__).parent / "golden" / "feedback_loop.yaml"
_CASES = yaml.safe_load(_GOLDEN.read_text())["cases"]
_VALID_CATEGORIES = {"positive", "negative", "neutral"}
_VALID_TIERS = {"keyword", "llm"}


@pytest.mark.parametrize("case", _CASES, ids=lambda c: c["id"])
def test_case_schema(case: dict) -> None:
    assert case["tier"] in _VALID_TIERS, f"{case['id']}: bad tier {case['tier']!r}"
    assert case["expected"] in _VALID_CATEGORIES, (
        f"{case['id']}: bad expected {case['expected']!r}"
    )
    assert case["comments"] and all(isinstance(c, str) for c in case["comments"])
    assert isinstance(case.get("days_since", 0), int)


_KEYWORD_CASES = [c for c in _CASES if c["tier"] == "keyword"]


@pytest.mark.parametrize("case", _KEYWORD_CASES, ids=lambda c: c["id"])
def test_keyword_tier_matches_golden(case: dict) -> None:
    from app.server.agents.feedback_loop import _detect_signal  # noqa: PLC0415 — see NOTE above

    got = _detect_signal(
        list(case["comments"]),
        case.get("state", ""),
        days_since=case.get("days_since", 0),
        pipeline_id=case["id"],
    )
    assert got == case["expected"], (
        f"{case['id']}: _detect_signal returned {got!r}, golden says {case['expected']!r}"
    )


def test_suite_has_keyword_coverage() -> None:
    """The suite must always contain keyword-tier cases so keyless CI asserts
    real behaviour, not just schema."""
    assert len(_KEYWORD_CASES) >= 2
