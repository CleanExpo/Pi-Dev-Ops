"""Validation of sealed startup receipts against current repository evidence."""
from __future__ import annotations

import hmac
from pathlib import Path
from typing import Any

from app.server.routing_schema import RoutingValidationError
from app.server.task_routing import decide_route
from senior_harness import digest
from setup_common import (
    GIT_SHA_PATTERN,
    GRILL_INTERACTIONS,
    SEAL_PREFIX,
    SETUP_SCHEMA_VERSION,
    STARTUP_ADMISSION,
    STARTUP_AUTHORITY,
    SetupError,
    _canonical_json,
    _interaction_for_objective,
    _is_sha256_digest,
)
from setup_receipts import _check_control_bindings, _receipt_seal
from setup_repository import _repository_snapshot


def _receipt_envelope_errors(receipt: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    observed_seal = receipt.get("receipt_seal")
    if not isinstance(observed_seal, str) or not observed_seal.startswith(SEAL_PREFIX):
        errors.append("startup receipt seal is missing or malformed")
    elif not hmac.compare_digest(observed_seal, _receipt_seal(receipt)):
        errors.append("startup receipt seal does not match this machine's harness key")
    candidate = {key: value for key, value in receipt.items() if key != "receipt_seal"}
    observed_digest = candidate.pop("receipt_integrity_digest", None)
    if not _is_sha256_digest(observed_digest):
        errors.append("startup receipt integrity digest is missing or malformed")
    elif observed_digest != digest(candidate):
        errors.append("startup receipt integrity digest is invalid")
    if receipt.get("stage") != "startup-admitted":
        errors.append("startup receipt stage is invalid")
    if receipt.get("admission") != STARTUP_ADMISSION:
        errors.append("startup receipt cannot grant mutation, business, or irreversible authority")
    contract = receipt.get("setup_contract")
    if not isinstance(contract, dict):
        errors.append("startup receipt is missing its setup contract")
        contract = {}
    return contract, errors


def _contract_identity_errors(contract: dict[str, Any], literal: str | None) -> list[str]:
    errors: list[str] = []
    embedded = dict(contract)
    embedded_digest = embedded.pop("setup_contract_digest", None)
    if not _is_sha256_digest(embedded_digest):
        errors.append("embedded setup contract digest is missing or malformed")
    elif embedded_digest != digest(embedded):
        errors.append("embedded setup contract digest is invalid")
    if literal is not None and contract.get("literal_objective") != literal:
        errors.append("literal objective differs from the frozen startup objective")
    objective = contract.get("literal_objective")
    if contract.get("schema_version") != SETUP_SCHEMA_VERSION or contract.get("stage") != "setup-contract":
        errors.append("embedded setup contract schema or stage is invalid")
    if not isinstance(objective, str) or not objective.strip():
        errors.append("embedded setup contract literal objective is invalid")
    else:
        if contract.get("task_id") != digest({"task": objective})[7:23]:
            errors.append("embedded setup contract task id is invalid")
        if contract.get("objective_digest") != digest({"task": objective}):
            errors.append("embedded setup contract objective digest is invalid")
    return errors


def _contract_policy_errors(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if contract.get("secondary_objectives") != []:
        errors.append("embedded setup contract cannot pre-authorize secondary objectives")
    interaction = contract.get("interaction")
    if interaction not in {"delivery", *GRILL_INTERACTIONS}:
        errors.append("embedded setup contract interaction is invalid")
    expected = _interaction_for_objective(contract.get("literal_objective"))
    if expected is not None and interaction != expected:
        errors.append("embedded setup contract interaction does not match the frozen literal objective")
    if contract.get("authority") != STARTUP_AUTHORITY:
        errors.append("setup contract cannot grant mutation, business, or irreversible authority")
    controller = contract.get("delivery_controller")
    valid_controller = (
        isinstance(controller, dict) and controller.get("skill_id") == "unlazy"
        and controller.get("required") is True
    )
    if not valid_controller:
        errors.append("startup receipt does not require Unlazy delivery control")
    return errors


def _routing_errors(contract: dict[str, Any]) -> list[str]:
    request = contract.get("routing_request")
    if not isinstance(request, dict) or request.get("task") != contract.get("literal_objective"):
        return ["routing request does not preserve the frozen startup objective"]
    try:
        current = decide_route(request).to_dict()
    except RoutingValidationError as exc:
        return [f"routing request is invalid: {exc}"]
    if _canonical_json(current) != _canonical_json(contract.get("route_decision")):
        return ["route decision changed after startup admission"]
    return []


def _repository_shape(contract: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    value = contract.get("repository")
    repository = value if isinstance(value, dict) else {}
    errors = [] if isinstance(value, dict) else ["embedded setup contract repository is invalid"]
    worktree = repository.get("worktree")
    if not isinstance(worktree, str) or not worktree or not Path(worktree).is_absolute():
        errors.append("repository worktree path is missing or invalid")
    head = repository.get("head_sha")
    if not isinstance(head, str) or GIT_SHA_PATTERN.fullmatch(head) is None:
        errors.append("repository head SHA is missing or malformed")
    if not isinstance(repository.get("dirty"), bool):
        errors.append("repository dirty flag is invalid")
    if not _is_sha256_digest(repository.get("worktree_state_digest")):
        errors.append("repository state digest is missing or malformed")
    return repository, errors


def _repository_drift_errors(
    repository: dict[str, Any], project: str | Path | None
) -> list[str]:
    bound = project if project is not None else repository.get("worktree")
    if bound is None:
        return []
    try:
        current = _repository_snapshot(Path(bound).resolve(), strict_clean=False)
    except (OSError, TypeError, SetupError) as exc:
        return exc.errors if isinstance(exc, SetupError) else [f"repository path is invalid: {exc}"]
    return [
        f"repository {field} changed after startup admission"
        for field in ("worktree", "head_sha", "dirty", "worktree_state_digest")
        if repository.get(field) != current.get(field)
    ]


def validate_startup_receipt(
    receipt: dict[str, Any], *, literal_objective: str | None = None,
    project: str | Path | None = None, verify_repository: bool = True,
    verify_control_bindings: bool = True,
) -> dict[str, Any]:
    """Re-probe all bound local evidence and reject stale or altered receipts."""
    if not isinstance(receipt, dict):
        raise SetupError(["startup receipt must be a JSON object"])
    contract, errors = _receipt_envelope_errors(receipt)
    errors.extend(_contract_identity_errors(contract, literal_objective))
    errors.extend(_contract_policy_errors(contract))
    errors.extend(_routing_errors(contract))
    repository, shape_errors = _repository_shape(contract)
    errors.extend(shape_errors)
    if verify_repository:
        errors.extend(_repository_drift_errors(repository, project))
    bindings = _check_control_bindings(receipt, verify_current=verify_control_bindings)
    errors.extend(bindings.integrity_failures)
    if verify_control_bindings:
        errors.extend(bindings.drift)
    if errors:
        raise SetupError(errors)
    return {
        "status": "valid", "task_id": contract["task_id"],
        "objective_digest": contract["objective_digest"],
        "head_sha": repository["head_sha"],
        "enforcement_scope": "mediated-nonmutating-dispatch",
    }
