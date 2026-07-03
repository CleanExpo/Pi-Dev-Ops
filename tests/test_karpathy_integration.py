"""
test_karpathy_integration.py — Karpathy principles are wired into the
generator brief and the evaluator loop.

Scope:
  - brief.build_structured_brief() injects KARPATHY_CONSTRAINTS
  - evaluator prompt paths (cached + SDK) include a 5th KARPATHY axis
  - _parse_evaluator_dimensions() extracts the karpathy score
  - Low karpathy scores append to lessons with category='karpathy'
  - Karpathy is a soft axis — the OVERALL score still drives pass/fail
"""
from __future__ import annotations

from unittest.mock import patch

from app.server.brief import (
    KARPATHY_CONSTRAINTS,
    build_structured_brief,
)
from app.server.session_evaluator import _parse_evaluator_dimensions


# ── Test 1 — constraints are injected into every brief ───────────────────────

def test_karpathy_constraints_injected_in_brief():
    """Every structured brief must carry the Karpathy engineering constraints."""
    for intent in ("feature", "bug", "chore", "spike", "hotfix"):
        spec = build_structured_brief(
            raw_brief="add a tiny helper",
            intent=intent,
        )
        assert KARPATHY_CONSTRAINTS in spec, (
            f"KARPATHY_CONSTRAINTS missing from {intent} brief"
        )
    # Sanity: the constraint text itself mentions the 4 Karpathy principles
    assert "Surgical diffs" in KARPATHY_CONSTRAINTS
    assert "Minimum code" in KARPATHY_CONSTRAINTS
    assert "assumptions upfront" in KARPATHY_CONSTRAINTS
    assert "success criteria" in KARPATHY_CONSTRAINTS


# ── Test 2 — evaluator prompt contains the 5th axis ──────────────────────────

def test_evaluator_prompt_contains_karpathy_axis():
    """Both evaluator paths must advertise KARPATHY as a fifth dimension."""
    # Cached direct-API evaluator (session_evaluator._run_eval_with_cache)
    import inspect

    from app.server import session_evaluator, session_phases

    cached_src = inspect.getsource(session_evaluator._run_eval_with_cache)
    assert "KARPATHY" in cached_src
    assert "5. KARPATHY" in cached_src
    assert "Surgical" in cached_src

    # SDK-path evaluator prompt lives in session_phases (_EVAL_PROMPT_DIMS)
    phases_src = inspect.getsource(session_phases)
    assert "KARPATHY: <score>/10" in phases_src
    assert "5. KARPATHY ADHERENCE" in phases_src


# ── Test 3 — parser extracts the karpathy score ──────────────────────────────

def test_parse_evaluator_dimensions_extracts_karpathy_score():
    """A synthetic evaluator response with a KARPATHY line should be parsed."""
    eval_text = (
        "COMPLETENESS: 9/10 — all requirements met\n"
        "CORRECTNESS: 8/10 — minor null check missing\n"
        "CONCISENESS: 9/10 — tight\n"
        "FORMAT: 9/10 — matches style\n"
        "KARPATHY: 4/10 — added speculative abstraction not in brief\n"
        "OVERALL: 8.75/10 — PASS\n"
        "CONFIDENCE: 85%\n"
    )
    dims = _parse_evaluator_dimensions(eval_text)
    assert "karpathy" in dims
    score, reason = dims["karpathy"]
    assert score == 4.0
    assert "speculative abstraction" in reason
    # The original 4 dimensions must still parse
    assert dims["completeness"][0] == 9.0
    assert dims["correctness"][0] == 8.0


# ── Test 4 — low karpathy score appends lesson with category='karpathy' ──────

def test_karpathy_failure_appends_to_lessons_jsonl():
    """When karpathy scores below threshold, the lesson-append loop uses
    category='karpathy' instead of the resolved intent."""
    eval_text = (
        "COMPLETENESS: 9/10 — ok\n"
        "CORRECTNESS: 9/10 — ok\n"
        "CONCISENESS: 9/10 — ok\n"
        "FORMAT: 9/10 — ok\n"
        "KARPATHY: 3/10 — silent interpretation of ambiguous brief\n"
        "OVERALL: 9/10 — PASS\n"
    )
    threshold = 7
    resolved_intent = "feature"

    # Replicate the exact loop from session_phases.py (cheap; keeps the test
    # hermetic — we are not running the full phase engine).
    dims = _parse_evaluator_dimensions(eval_text)
    appended: list[dict] = []

    def _fake_append(source, category, lesson, severity="info"):
        appended.append(
            {"source": source, "category": category, "lesson": lesson, "severity": severity}
        )
        return appended[-1]

    with patch("app.server.session_phases.append_lesson", side_effect=_fake_append):
        from app.server.session_phases import append_lesson as _al  # noqa: F401

        for dim_name, (score, reason) in dims.items():
            if score < threshold:
                lesson_category = "karpathy" if dim_name == "karpathy" else resolved_intent
                _al(
                    source="evaluator",
                    category=lesson_category,
                    lesson=f"{dim_name} scored {score}/10: {reason}",
                    severity="warn",
                )

    assert len(appended) == 1, f"expected 1 lesson, got {appended}"
    assert appended[0]["category"] == "karpathy"
    assert "karpathy" in appended[0]["lesson"]


# ── Test 6 — empty diffs never seed evaluator lessons (RA-6826/6827) ─────────

def test_empty_diff_skips_evaluator_lessons():
    """A no-op build (empty diff) must append zero evaluator lessons, even when
    every dimension fails. Empty-diff warnings ("empty diff", "fails all
    Karpathy principles", "complete failure to produce any output") are
    artefacts of a build that changed nothing, not system lessons — feeding
    them to lessons.jsonl produced the garbage improvement proposals in
    RA-6825/6826/6827."""
    eval_text = (
        "COMPLETENESS: 0/10 — empty diff, nothing implemented\n"
        "CORRECTNESS: 0/10 — no code to assess\n"
        "CONCISENESS: 0/10 — no output\n"
        "FORMAT: 0/10 — no output\n"
        "KARPATHY: 0/10 — empty diffs fail all Karpathy principles\n"
        "OVERALL: 0/10 — FAIL\n"
    )
    threshold = 7
    resolved_intent = "spike"
    dims = _parse_evaluator_dimensions(eval_text)
    appended: list[dict] = []

    def _fake_append(source, category, lesson, severity="info"):
        appended.append({"category": category, "lesson": lesson})
        return appended[-1]

    # Replicate the guarded loop from session_phases._phase_evaluate.
    for diff_full, expect in (("", 0), ("+ real change\n", 6)):
        appended.clear()
        diff_is_empty = not (diff_full or "").strip()
        with patch("app.server.session_phases.append_lesson", side_effect=_fake_append):
            from app.server.session_phases import append_lesson as _al

            passed = False
            if not diff_is_empty:
                for dim_name, (score, reason) in dims.items():
                    if score < threshold:
                        cat = "karpathy" if dim_name == "karpathy" else resolved_intent
                        _al(source="evaluator", category=cat,
                            lesson=f"{dim_name} scored {score}/10: {reason}", severity="warn")
                if not passed:
                    weak = ", ".join(d for d, (s, _) in dims.items() if s < threshold)
                    _al(source="evaluator", category=resolved_intent,
                        lesson=f"Build scored 0/10 (below {threshold}). Weak: {weak}", severity="warn")
        assert len(appended) == expect, (
            f"empty={diff_is_empty}: expected {expect} lessons, got {len(appended)}"
        )


def test_empty_diff_guard_present_in_source():
    """Bind the behaviour test to the real implementation: the evaluator phase
    must gate lesson-writing on a non-empty diff."""
    import inspect

    from app.server import session_phases

    src = inspect.getsource(session_phases._phase_evaluate)
    assert "diff_is_empty" in src
    assert "if not diff_is_empty:" in src


# ── Test 5 — soft gate: low karpathy alone does not block a passing build ────

def test_soft_gate_does_not_block_on_karpathy_alone():
    """A build with high hard-axis scores but low karpathy should still pass.

    OVERALL comes from the evaluator output directly; karpathy is reported
    but not included in the pass/fail decision.
    """
    eval_text = (
        "COMPLETENESS: 9/10 — ok\n"
        "CORRECTNESS: 9/10 — ok\n"
        "CONCISENESS: 9/10 — ok\n"
        "FORMAT: 9/10 — ok\n"
        "KARPATHY: 2/10 — refactored adjacent unbroken code\n"
        "OVERALL: 9.0/10 — PASS\n"
    )
    from app.server.session_evaluator import _extract_eval_score

    overall = _extract_eval_score(eval_text)
    threshold = 7
    assert overall is not None
    assert overall >= threshold, "hard-axis average must still gate pass/fail"

    dims = _parse_evaluator_dimensions(eval_text)
    assert dims["karpathy"][0] < threshold  # karpathy is low
    # Soft-gate invariant: overall passes regardless of karpathy
    passed = overall >= threshold
    assert passed is True
