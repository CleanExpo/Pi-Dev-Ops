"""Orchestrate the labelled synthetic Nexus One vertical journey."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from .entry import (
    DEFAULT_AUTHORISED,
    DEFAULT_HYPOTHESIS,
    DEFAULT_METHOD,
    accept_or_resume,
    evidence_for,
    run_method,
    utc_now,
)
from .policy import BUILDER_FAMILY, select_worker
from .review import invoke_independent_review
from .store import SyntheticStore
from .types import (
    LINEAGE,
    MAX_LANE,
    IndependentReview,
    JourneyResult,
    MethodAttempt,
    Receipt,
    TaskContract,
    WorkerDecision,
    receipt_from_dict,
)


def _checkpoint_sha(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _persist_receipt(
    store: SyntheticStore,
    task: TaskContract,
    worker: WorkerDecision,
    review: IndependentReview,
    evidence: tuple[str, ...],
    accepted: bool,
    checkpoint: dict[str, Any],
) -> Receipt:
    path = store.write_checkpoint(task.task_id, checkpoint)
    receipt = Receipt(
        receipt_id=f"rcpt-{task.task_id}",
        task_id=task.task_id,
        lineage=LINEAGE,
        excluded_from_real_acceptance=True,
        evidence=evidence,
        checkpoint_sha256=_checkpoint_sha(checkpoint),
        accepted=accepted,
        worker=worker,
        review=review,
        path=str(path),
    )
    store.write_receipt(receipt)
    return receipt


def _hold(
    store: SyntheticStore,
    task: TaskContract,
    *,
    duplicate: bool,
    resumed: bool,
    worker: WorkerDecision,
    status: str,
) -> JourneyResult:
    updated = TaskContract(**{**task.to_dict(), "status": status})
    store.put_task(updated)
    checkpoint = {
        "excluded_from_real_acceptance": True,
        "lineage": LINEAGE,
        "reason": worker.reason,
        "status": status,
        "task_id": task.task_id,
        "updated_at": utc_now(),
    }
    path = store.write_checkpoint(task.task_id, checkpoint)
    return JourneyResult(
        task=updated,
        duplicate=duplicate,
        resumed=resumed,
        dispatched=False,
        accepted=False,
        worker=worker,
        checkpoint_path=str(path),
    )


def run_pilot(
    store: SyntheticStore,
    *,
    founder_id: str,
    objective: str,
    platform: str = "linux",
    requested_lane: str | None = None,
    resume_task_id: str | None = None,
    new_task_token: str = "",
    authorised: Iterable[str] = DEFAULT_AUTHORISED,
    method: str = DEFAULT_METHOD,
    hypothesis: str = DEFAULT_HYPOTHESIS,
    inject_failure: bool = False,
    capacity_depleted: bool = False,
    omit_evidence: bool = False,
) -> JourneyResult:
    """Run the labelled synthetic journey. Happy path never needs API keys."""
    task, duplicate, resumed = accept_or_resume(
        store,
        founder_id=founder_id,
        objective=objective,
        resume_task_id=resume_task_id,
        new_task_token=new_task_token,
        authorised=authorised,
    )
    worker = select_worker(
        platform=platform,
        requested_lane=requested_lane,
        capacity_depleted=capacity_depleted,
    )
    if not worker.eligible:
        status = "checkpointed" if worker.reason.startswith("capacity_") else "refused"
        return _hold(store, task, duplicate=duplicate, resumed=resumed, worker=worker, status=status)
    if duplicate or resumed:
        return _replay_existing(store, task, worker, duplicate=duplicate, resumed=resumed)
    return _dispatch(store, task, worker, method, hypothesis, inject_failure, omit_evidence)


def _replay_existing(
    store: SyntheticStore,
    task: TaskContract,
    worker: WorkerDecision,
    *,
    duplicate: bool,
    resumed: bool,
) -> JourneyResult:
    checkpoint = store.load_checkpoint(task.task_id) or {}
    raw = store.load_receipt(f"rcpt-{task.task_id}")
    receipt = None if raw is None else receipt_from_dict(raw)
    return JourneyResult(
        task=task,
        duplicate=duplicate,
        resumed=resumed,
        dispatched=False,
        accepted=bool(checkpoint.get("accepted")),
        worker=worker,
        attempts=tuple(store.list_attempts(task.task_id)),
        review=None if receipt is None else receipt.review,
        receipt=receipt,
        checkpoint_path=str(store.root / "checkpoints" / f"{task.task_id}.json"),
        evidence=tuple(checkpoint.get("evidence") or ()),
    )


def _is_accepted(attempt_ok: bool, review: IndependentReview, worker: WorkerDecision) -> bool:
    return (
        attempt_ok
        and review.verdict == "pass"
        and worker.lane == MAX_LANE
        and worker.cost_usd == 0.0
    )


def _checkpoint(
    task: TaskContract,
    worker: WorkerDecision,
    review: IndependentReview,
    evidence: tuple[str, ...],
    accepted: bool,
    attempt_row: dict[str, Any],
) -> dict[str, Any]:
    status = "accepted" if accepted else "failed"
    return {
        "accepted": accepted,
        "attempts": [attempt_row],
        "billing": worker.billing,
        "cost_usd": worker.cost_usd,
        "evidence": list(evidence),
        "excluded_from_real_acceptance": True,
        "lane": worker.lane,
        "lineage": LINEAGE,
        "review": review.to_dict(),
        "status": status,
        "task_id": task.task_id,
        "updated_at": utc_now(),
    }


def _dispatch(
    store: SyntheticStore,
    task: TaskContract,
    worker: WorkerDecision,
    method: str,
    hypothesis: str,
    inject_failure: bool,
    omit_evidence: bool,
) -> JourneyResult:
    attempt = run_method(
        store, task, method=method, hypothesis=hypothesis, inject_failure=inject_failure
    )
    evidence = () if omit_evidence else evidence_for(task, attempt)
    review = invoke_independent_review(
        builder_family=BUILDER_FAMILY,
        evidence=evidence,
        worker_claims_done=attempt.outcome == "passed",
    )
    accepted = _is_accepted(attempt.outcome == "passed", review, worker)
    updated = TaskContract(**{**task.to_dict(), "status": "accepted" if accepted else "failed"})
    store.put_task(updated)
    receipt = _persist_receipt(
        store,
        updated,
        worker,
        review,
        evidence,
        accepted,
        _checkpoint(updated, worker, review, evidence, accepted, attempt.to_dict()),
    )
    return _dispatched_result(updated, worker, attempt, review, receipt, evidence)


def _dispatched_result(
    task: TaskContract,
    worker: WorkerDecision,
    attempt: MethodAttempt,
    review: IndependentReview,
    receipt: Receipt,
    evidence: tuple[str, ...],
) -> JourneyResult:
    return JourneyResult(
        task=task,
        duplicate=False,
        resumed=False,
        dispatched=True,
        accepted=task.status == "accepted",
        worker=worker,
        attempts=(attempt,),
        review=review,
        receipt=receipt,
        checkpoint_path=receipt.path,
        evidence=evidence,
    )
