"""UNI-2652 planted-failure proofs, including a control that can go red."""
from __future__ import annotations

from pathlib import Path

from scripts.golden_journey_planted import PlantedProof, run_planted_failure


def test_planted_failure_proves_all_five_facts(tmp_path: Path):
    proof = run_planted_failure(tmp_path)
    assert proof.errors == []
    assert proof.worktree_retained is True
    assert proof.claim_released_after_expiry is True
    assert proof.second_machine_resumed is True
    assert proof.no_duplicate_claim is True
    assert proof.no_false_green is True
    assert proof.all_passed() is True


def test_all_passed_fails_if_the_killed_run_reported_green():
    """Positive control: a false PASS must make the planted journey red."""
    proof = PlantedProof(
        worktree_retained=True,
        claim_released_after_expiry=True,
        second_machine_resumed=True,
        no_duplicate_claim=True,
        no_false_green=False,
    )
    assert proof.all_passed() is False
