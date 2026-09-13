"""Independent Judge hook for the synthetic Nexus One pilot.

Deterministic on purpose: ``prebuild_judge`` / ``tao_judge`` call models
and would require API credits. This hook records an independent-family
verdict without spending. SYNTHETIC: not a live Judge report.
"""
from __future__ import annotations

from .policy import REVIEW_FAMILY
from .types import IndependentReview


def invoke_independent_review(
    *,
    builder_family: str,
    evidence: tuple[str, ...],
    worker_claims_done: bool,
) -> IndependentReview:
    """Different family from the builder. Missing evidence is not a pass."""
    if builder_family == REVIEW_FAMILY:
        return _review("rejected", 0, "same_family_review", builder_family)
    if not evidence or (worker_claims_done and not evidence):
        return _review("incomplete", 0, "missing_evidence", builder_family)
    if any(not item.startswith("synthetic:") for item in evidence):
        return _review("rejected", 0, "unlabelled_evidence", builder_family)
    return _review("pass", 100, "scoped_synthetic_evidence", builder_family)


def _review(
    verdict: str, score: int, reason: str, builder_family: str
) -> IndependentReview:
    return IndependentReview(
        invoked=True,
        independent=builder_family != REVIEW_FAMILY,
        family=REVIEW_FAMILY,
        builder_family=builder_family,
        verdict=verdict,  # type: ignore[arg-type]
        score=score,
        reason=reason,
    )
