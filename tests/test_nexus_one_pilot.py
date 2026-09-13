"""Deterministic tests for the Nexus One SYNTHETIC vertical pilot.

No network, no Anthropic API, no Claude CLI. Coverage: T01 authorised
complete; T02 duplicate input; T11/T12 failed-method fingerprint; plus
Max-only, Windows refuse, durable receipt, and Judge-hook independence.
"""
from __future__ import annotations

import pytest

from app.server.nexus_one import (
    LINEAGE,
    SYNTHETIC_MARKER,
    SyntheticStore,
    accept_or_resume,
    run_method,
    run_pilot,
    select_worker,
)
from app.server.nexus_one.entry import DEFAULT_HYPOTHESIS, DEFAULT_METHOD
from app.server.nexus_one.policy import BUILDER_FAMILY, REVIEW_FAMILY
from app.server.nexus_one.types import MAX_LANE

OBJECTIVE = f"{SYNTHETIC_MARKER} complete the labelled nexus-one fixture"


def _store(tmp_path) -> SyntheticStore:
    return SyntheticStore(tmp_path / "nx1")


def _run(store: SyntheticStore, **kwargs):
    params = {
        "founder_id": "phill",
        "objective": OBJECTIVE,
        "platform": "linux",
    }
    params.update(kwargs)
    return run_pilot(store, **params)


def test_authorised_synthetic_task_completes_with_scoped_evidence(tmp_path):
    result = _run(_store(tmp_path))
    assert result.accepted is True
    assert result.dispatched is True
    assert result.duplicate is False
    assert result.task.lineage == LINEAGE
    assert result.worker.lane == MAX_LANE
    assert result.worker.billing == "subscription"
    assert result.worker.cost_usd == 0.0
    assert result.evidence
    assert all(item.startswith("synthetic:") for item in result.evidence)
    assert result.review is not None
    assert result.review.invoked is True
    assert result.review.independent is True
    assert result.review.family == REVIEW_FAMILY
    assert result.review.builder_family == BUILDER_FAMILY
    assert result.receipt is not None
    assert result.receipt.excluded_from_real_acceptance is True
    assert result.receipt.accepted is True
    assert result.checkpoint_path


def test_duplicate_input_does_not_create_a_second_task(tmp_path):
    store = _store(tmp_path)
    first = _run(store)
    second = _run(store)
    assert first.task.task_id == second.task.task_id
    assert second.duplicate is True
    assert second.dispatched is False
    assert len(list((store.root / "tasks").glob("*.json"))) == 1


def test_failed_method_fingerprint_rejects_identical_retry(tmp_path):
    store = _store(tmp_path)
    failed = _run(store, inject_failure=True)
    assert failed.accepted is False
    assert failed.attempts[0].outcome == "failed"
    fingerprint = failed.attempts[0].fingerprint
    retry = run_method(
        store,
        failed.task,
        method=DEFAULT_METHOD,
        hypothesis=DEFAULT_HYPOTHESIS,
        inject_failure=True,
    )
    assert retry.fingerprint == fingerprint
    assert retry.outcome == "rejected_duplicate"
    outcomes = [item.outcome for item in store.list_attempts(failed.task.task_id)]
    assert outcomes == ["failed", "rejected_duplicate"]


def test_windows_worker_is_refused():
    decision = select_worker(platform="win32")
    assert decision.eligible is False
    assert decision.reason == "windows_review_only"


def test_api_billing_lane_is_refused_even_on_mac():
    decision = select_worker(platform="darwin", requested_lane="anthropic_api")
    assert decision.eligible is False
    assert decision.reason == "api_billing_forbidden"
    assert decision.cost_usd == 0.0


def test_unauthorised_founder_is_rejected(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(PermissionError, match="not authorised"):
        _run(store, founder_id="stranger")


def test_unlabelled_objective_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="SYNTHETIC"):
        _run(_store(tmp_path), objective="do a real production deploy")


def test_resume_returns_the_same_contract(tmp_path):
    store = _store(tmp_path)
    first = _run(store)
    resumed = _run(store, resume_task_id=first.task.task_id)
    assert resumed.resumed is True
    assert resumed.duplicate is False
    assert resumed.task.task_id == first.task.task_id
    assert resumed.dispatched is False


def test_explicit_new_task_token_is_not_deduplicated(tmp_path):
    store = _store(tmp_path)
    first = _run(store)
    second = _run(store, new_task_token="deliberate-new")
    assert first.task.task_id != second.task.task_id
    assert second.duplicate is False


def test_capacity_depleted_checkpoints_without_paid_fallback(tmp_path):
    result = _run(_store(tmp_path), capacity_depleted=True)
    assert result.accepted is False
    assert result.dispatched is False
    assert result.task.status == "checkpointed"
    assert result.worker.reason == "capacity_depleted_no_paid_fallback"


def test_missing_evidence_keeps_task_unaccepted(tmp_path):
    result = _run(_store(tmp_path), omit_evidence=True)
    assert result.accepted is False
    assert result.review is not None
    assert result.review.verdict == "incomplete"
    assert result.task.status != "accepted"


def test_receipt_and_checkpoint_survive_store_reload(tmp_path):
    root = tmp_path / "nx1"
    first = _run(SyntheticStore(root))
    reloaded = SyntheticStore(root)
    task = reloaded.get_task(first.task.task_id)
    checkpoint = reloaded.load_checkpoint(first.task.task_id)
    receipt = reloaded.load_receipt(f"rcpt-{first.task.task_id}")
    assert task is not None
    assert task.status == "accepted"
    assert checkpoint is not None
    assert checkpoint["lineage"] == LINEAGE
    assert checkpoint["excluded_from_real_acceptance"] is True
    assert receipt is not None
    assert receipt["accepted"] is True
    assert receipt["worker"]["lane"] == MAX_LANE


def test_accept_or_resume_replay_is_idempotent(tmp_path):
    store = _store(tmp_path)
    first, dup1, _ = accept_or_resume(
        store, founder_id="phill", objective=OBJECTIVE
    )
    second, dup2, _ = accept_or_resume(
        store, founder_id="phill", objective=f"  {OBJECTIVE}  "
    )
    assert dup1 is False
    assert dup2 is True
    assert first.task_id == second.task_id
