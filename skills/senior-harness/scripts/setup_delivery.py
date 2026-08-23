"""Delivery dispatch admission bound to startup and Grill evidence."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from grill_session import (
    GrillSessionError,
    file_digest as grill_file_digest,
    validate_receipt as validate_grill_receipt,
    validate_session as validate_grill_session,
)
from senior_harness import MUTATING_KINDS, ready_moves, validate_contract
from setup_common import GRILL_INTERACTIONS, SetupError
from setup_validation import validate_startup_receipt


def _validate_grill_gate(
    setup: dict[str, Any], grill_session: dict[str, Any] | None
) -> None:
    if setup.get("interaction") not in GRILL_INTERACTIONS:
        return
    if not isinstance(grill_session, dict):
        raise SetupError(["Grill delivery remains stopped until a shared-understanding session is supplied"])
    if grill_session.get("state") != "confirmed":
        raise SetupError(["Grill delivery remains stopped until shared understanding is confirmed"])
    try:
        validate_grill_session(grill_session)
        validate_grill_receipt(grill_session.get("receipt", {}))
    except GrillSessionError as exc:
        raise SetupError([f"invalid Grill shared-understanding session: {exc}"]) from exc
    if grill_session.get("objective") != setup.get("literal_objective"):
        raise SetupError(["Grill objective differs from the frozen startup objective"])
    sketch = grill_session.get("sketch", {})
    sketch_path = Path(str(sketch.get("path", "")))
    if not sketch_path.is_file() or sketch.get("sha256") != grill_file_digest(sketch_path):
        raise SetupError(["Grill sketch changed after shared understanding was confirmed"])


def _validate_move(
    delivery_contract: dict[str, Any], move_id: str, problem_id: str | None
) -> None:
    moves = {move["move_id"]: move for move in delivery_contract.get("move_graph", [])}
    move = moves.get(move_id)
    if not move:
        raise SetupError([f"unknown delivery move: {move_id}"])
    if move.get("kind") in MUTATING_KINDS:
        raise SetupError([f"startup admission cannot authorize mutating move {move_id}"])
    stopped = {
        case.get("problem_id")
        for case in delivery_contract.get("uncertainty_cases", [])
        if case.get("status") == "open" and case.get("stop_current_path") is True
    }
    move_problem = problem_id or move.get("problem_id")
    if move_problem and move_problem in stopped:
        raise SetupError([f"problem {move_problem} is stopped by an open uncertainty case"])
    if move_id not in ready_moves(delivery_contract):
        raise SetupError([f"move {move_id} is not dispatch-ready"])


def guard_dispatch(
    delivery_contract: dict[str, Any], receipt: dict[str, Any], move_id: str, *,
    problem_id: str | None = None, grill_session: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Admit one nonmutating move after startup and anti-spin checks."""
    setup = receipt.get("setup_contract", {})
    validate_startup_receipt(
        receipt, literal_objective=delivery_contract.get("literal_request"),
        project=setup.get("repository", {}).get("worktree"),
    )
    _validate_grill_gate(setup, grill_session)
    validate_contract(delivery_contract)
    if delivery_contract.get("task_id") != setup.get("task_id"):
        raise SetupError(["delivery task id differs from the frozen startup task"])
    _validate_move(delivery_contract, move_id, problem_id)
    return {
        "status": "admitted", "move_id": move_id, "task_id": setup["task_id"],
        "mutation_authority": False,
    }
