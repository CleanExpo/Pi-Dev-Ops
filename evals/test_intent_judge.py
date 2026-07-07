"""Prove-It Gate — slice 2 (RA-7014): binary LLM-judge on intent classification.

Two layers:
  1. Pure-function tests (always run, incl. keyless CI): the judge prompt builder
     and the fail-closed verdict parser.
  2. Live-judge agreement test (skips without ANTHROPIC_API_KEY, so it no-ops in
     keyless CI): runs the Sonnet judge over the golden set and reports
     judge↔expert disagreement. NON-BLOCKING and advisory until the calibration
     harness (slice 3a) proves disagreement <20% — only then may it gate.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from evals.judge import build_prompt, judge_binary, parse_verdict

_GOLDEN = Path(__file__).parent / "golden" / "intent_classification.yaml"
_DATA = yaml.safe_load(_GOLDEN.read_text())
_RUBRIC = _DATA["rubric"]
_CASES = _DATA["cases"]

_HAVE_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))
# Advisory bar for slice 2 (the real <20% gate is set/enforced in slice 3a calibration).
_MAX_DISAGREEMENT = 0.20


# ── Layer 1: pure functions (always run) ─────────────────────────────────────
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("VERDICT: PASS", True),
        ("VERDICT: FAIL", False),
        ("verdict: pass", True),
        ("some preamble\nVERDICT: PASS\n", True),
        ("", False),  # fail-closed
        ("I think it's fine", False),  # unparseable → fail-closed
    ],
)
def test_parse_verdict_fail_closed(raw: str, expected: bool) -> None:
    assert parse_verdict(raw) is expected


def test_build_prompt_contains_candidate_and_rubric() -> None:
    p = build_prompt('{"message": "hi", "assigned_intent": "unknown"}', _RUBRIC)
    assert "assigned_intent" in p
    assert "research" in p  # rubric text present
    assert p.rstrip().endswith("VERDICT:")


def test_golden_dataset_is_balanced() -> None:
    """Guard: the set must contain both PASS and FAIL expectations, else the judge
    could score 100% by always answering one way."""
    passes = [c for c in _CASES if c["expected_pass"]]
    fails = [c for c in _CASES if not c["expected_pass"]]
    assert len(passes) >= 5 and len(fails) >= 5, "golden set must exercise both verdicts"
    assert len(_CASES) >= 15


# ── Layer 2: live judge agreement (skips without a key) ──────────────────────
@pytest.mark.skipif(not _HAVE_KEY, reason="no ANTHROPIC_API_KEY — live judge skipped (keyless CI)")
@pytest.mark.asyncio
async def test_judge_agreement_within_bar() -> None:
    disagreements: list[str] = []
    for c in _CASES:
        candidate = f'{{"message": {c["message"]!r}, "assigned_intent": {c["assigned_intent"]!r}}}'
        verdict = await judge_binary(candidate, _RUBRIC)
        if verdict.passed != c["expected_pass"]:
            disagreements.append(
                f"{c['message']!r} as {c['assigned_intent']}: "
                f"judge={'PASS' if verdict.passed else 'FAIL'} expert={'PASS' if c['expected_pass'] else 'FAIL'}"
            )
    rate = len(disagreements) / len(_CASES)
    detail = "\n".join(disagreements)
    assert rate <= _MAX_DISAGREEMENT, (
        f"judge↔expert disagreement {rate:.0%} > {_MAX_DISAGREEMENT:.0%}:\n{detail}"
    )
