"""RA-7016 regression — the precision heuristic must not punish the classify pass.

Before the fix, precision was regex_count/total, so a single correct Claude
classify catch dropped precision to <0.95 and flipped `passed` to False — which
aborted the cross-chat send path (draft_review._do_send, strictness=high). These
tests pin the corrected contract: classify hits are trusted, and `passed` fails
only on genuine classifier degradation.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from swarm.pii_redactor import Hit, redact  # noqa: E402


def _location_stub(text: str) -> list[Hit]:
    """Deterministic classifier stub: catches the literal 'Springfield'."""
    idx = text.find("Springfield")
    if idx < 0:
        return []
    return [Hit("LOCATION", idx, idx + len("Springfield"), "classify", "[LOCATION-REDACTED]")]


def test_standard_no_classifier_passes() -> None:
    result = redact("Email john@example.com", strictness="standard")
    assert result.passed is True
    assert result.precision_score == 1.0
    assert result.regex_hits == 1
    assert result.classify_hits == 0


def test_correct_classify_catch_does_not_fail_precision() -> None:
    # The exact RA-7016 scenario: one regex hit (email) + one correct classify
    # hit (LOCATION). Old heuristic scored 1/2 = 0.5 -> passed False.
    text = "Email john@example.com, meet in Springfield."
    result = redact(text, strictness="high", claude_classify=_location_stub)
    assert result.passed is True
    assert result.precision_score == 1.0
    assert result.regex_hits == 1
    assert result.classify_hits == 1
    assert "[LOCATION-REDACTED]" in result.redacted_payload
    assert "[EMAIL-REDACTED]" in result.redacted_payload


def test_classify_only_hit_passes() -> None:
    # No regex-detectable PII, one classify catch. Old heuristic: 0/1 = 0.0.
    result = redact("meet in Springfield", strictness="high", claude_classify=_location_stub)
    assert result.passed is True
    assert result.regex_hits == 0
    assert result.classify_hits == 1


def test_degraded_when_expected_classifier_errors() -> None:
    def _boom(_text: str) -> list[Hit]:
        raise RuntimeError("classifier down")

    result = redact("Email john@example.com", strictness="high", claude_classify=_boom)
    assert result.passed is False  # fail-closed: expected classify could not run
    assert result.precision_score == 0.0
    # regex still redacts on the fallback path
    assert result.regex_hits == 1
    assert "[EMAIL-REDACTED]" in result.redacted_payload


def test_standard_with_explicit_classifier_error_is_degraded() -> None:
    def _boom(_text: str) -> list[Hit]:
        raise RuntimeError("down")

    # An explicitly-supplied classifier that errors is a degradation regardless
    # of strictness.
    result = redact("hello", strictness="standard", claude_classify=_boom)
    assert result.passed is False
