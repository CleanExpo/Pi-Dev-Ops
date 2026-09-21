"""RA-7596 — Pipeline Smoke A4 is generate + fail-closed verify, not a ship."""
from __future__ import annotations

from scripts.smoke_pipeline_resilience import is_expected_smoke_verify_terminal
from scripts.smoke_test_pipeline import PipelineAssertions, _apply_terminal


# Quiet-tip run 35547546822 after RA-7546/#793 CLEAR.
_EVIDENCE_ROW = {
    "id": "bc465a1e3877",
    "status": "blocked",
    "last_phase": "generator",
    "lines": 100,
    "files_modified": 0,
    "error": "Release blocked by evaluator: verification_failed",
}


def test_evidence_run_is_documented_verify_terminal() -> None:
    assert is_expected_smoke_verify_terminal(_EVIDENCE_ROW) is True


def test_honesty_fix_last_phase_evaluator_still_matches() -> None:
    row = dict(_EVIDENCE_ROW, last_phase="evaluator", evaluator_status="verification_failed")
    assert is_expected_smoke_verify_terminal(row) is True


def test_planner_block_is_not_a_verify_terminal() -> None:
    row = {
        "status": "blocked",
        "last_phase": "sandbox",
        "error": "Plan blocked: planner returned exit status 1",
    }
    assert is_expected_smoke_verify_terminal(row) is False


def test_product_warned_evaluator_is_not_a_verify_terminal() -> None:
    row = {
        "status": "blocked",
        "last_phase": "evaluator",
        "evaluator_status": "warned",
        "error": "Release blocked by evaluator: warned",
    }
    assert is_expected_smoke_verify_terminal(row) is False


def test_complete_is_not_classified_as_verify_terminal() -> None:
    assert is_expected_smoke_verify_terminal({
        "status": "complete", "last_phase": "push", "files_modified": 1,
    }) is False


def test_apply_terminal_evidence_row_passes_a4_without_pr() -> None:
    pa = PipelineAssertions(
        spawned=True, entered_generate=True, generate_duration_s=44.1,
    )
    _apply_terminal(pa, _EVIDENCE_ROW)
    assert pa.documented_verify_terminal is True
    assert pa.reached_complete is False
    assert pa.errors == []
    assert pa.all_passed() is True
    assert "documented verify-terminal" in pa.summary()
    assert "n/a (verify-terminal)" in pa.summary()


def test_ship_path_still_requires_complete_files_and_pr() -> None:
    pa = PipelineAssertions(
        spawned=True, entered_generate=True, generate_duration_s=44.1,
        reached_complete=True, files_modified=1,
    )
    assert pa.all_passed() is False
    pa.pr_url = "https://github.com/CleanExpo/Pi-Dev-Ops/pull/1"
    assert pa.all_passed() is True


def test_verify_terminal_still_fails_if_generate_never_entered() -> None:
    pa = PipelineAssertions(spawned=True, generate_duration_s=44.1)
    _apply_terminal(pa, _EVIDENCE_ROW)
    assert pa.documented_verify_terminal is True
    assert pa.all_passed() is False
