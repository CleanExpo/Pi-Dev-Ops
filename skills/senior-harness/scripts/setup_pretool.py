"""PreToolUse lifecycle handler and active-receipt policy enforcement."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from setup_common import GRILL_INTERACTIONS, SetupError, _hook_output
from setup_prompt import _new_contract
from setup_receipts import _check_control_bindings, admit_startup
from setup_state import (
    _pending_quarantine_reason,
    _read_pending_objective,
    _read_state,
    _session_lock_path,
    _state_lock,
    _write_state,
)
from setup_tools import (
    _has_signed_dispatch_admission,
    _is_parallel_control_tool,
    _is_parallel_dispatch_tool,
    _is_parallel_verification_tool,
    _parallel_dispatch_context,
    _tool_is_grill_driver,
    _tool_is_recovery_safe,
)
from setup_validation import validate_startup_receipt


def _recover_pending(
    *, pending_path: Path, state_path: Path, session_id: str, surface: str,
    project_root: Path, roots: Iterable[str | Path] | None,
) -> tuple[bool, SetupError | None]:
    if state_path.is_file() or not pending_path.is_file():
        return False, None
    pending = _read_pending_objective(
        pending_path, session_id=session_id, surface=surface
    )
    try:
        contract = _new_contract(
            pending["literal_objective"], project_root, surface, roots, session_id
        )
        receipt = admit_startup(contract)
        _write_state(state_path, {"receipt": receipt, "first_tool_admitted": False})
        pending_path.unlink(missing_ok=True)
        return True, None
    except SetupError as exc:
        return False, exc


def _missing_state_response(
    recovery_safe: bool, admission_error: SetupError | None
) -> dict[str, Any]:
    if admission_error is not None:
        reason = f"pending startup objective cannot be admitted here ({admission_error})"
    else:
        reason = "no startup receipt exists for this session"
    if recovery_safe:
        return _hook_output(
            "PreToolUse",
            f"Senior Harness recovery-only read: {reason}. This permits evidence discovery only and grants no mutation, provider, worker, business, or irreversible authority.",
        )
    return _hook_output("PreToolUse", f"Senior Harness denied the tool: {reason}.", deny=True)


def _active_tool_state(state_path: Path, project_root: Path) -> tuple[Any, ...]:
    state = _read_state(state_path)
    receipt = state.get("receipt", {})
    if not isinstance(receipt, dict):
        raise SetupError(["startup state receipt must be a JSON object"])
    admitted = state.get("first_tool_admitted")
    if not isinstance(admitted, bool):
        raise SetupError(["startup state first_tool_admitted flag is invalid"])
    contract = receipt.get("setup_contract")
    if not isinstance(contract, dict):
        raise SetupError(["startup receipt is missing its setup contract"])
    interaction = contract.get("interaction")
    first_tool = not admitted
    validate_startup_receipt(
        receipt, project=project_root,
        verify_repository=first_tool or interaction in GRILL_INTERACTIONS,
        verify_control_bindings=False,
    )
    bindings = _check_control_bindings(receipt)
    if bindings.integrity_failures:
        raise SetupError([*bindings.integrity_failures, *bindings.drift])
    if bindings.drift and (first_tool or interaction in GRILL_INTERACTIONS):
        raise SetupError(list(bindings.drift))
    if first_tool:
        state["first_tool_admitted"] = True
        _write_state(state_path, state)
    return receipt, interaction, bindings.drift


def _invalid_state_response(exc: Exception, recovery_safe: bool) -> dict[str, Any]:
    if recovery_safe:
        return _hook_output(
            "PreToolUse",
            f"Senior Harness recovery-only read: startup state is invalid ({exc}). This permits evidence discovery only and grants no mutation, provider, worker, business, or irreversible authority.",
        )
    return _hook_output(
        "PreToolUse", f"Senior Harness denied the tool: invalid startup state ({exc}).",
        deny=True,
    )


def _parallel_denial(
    payload: dict[str, Any], project_root: Path, receipt: dict[str, Any],
    control_safe: bool,
) -> str | None:
    policy = receipt["setup_contract"].get("orchestration_policy", {})
    dispatch = _is_parallel_dispatch_tool(payload)
    admitted = dispatch and _has_signed_dispatch_admission(payload, project_root, receipt)
    allowed = (
        control_safe or _is_parallel_control_tool(payload) or admitted
        or _is_parallel_verification_tool(payload)
    )
    if not isinstance(policy, dict) or policy.get("parallel_required") is not True or allowed:
        return None
    if dispatch:
        return (
            "Senior Harness denied dispatch: generic agent spawning is not Unlazy admission; use the signed "
            "senior-harness.dispatch control wrapper with a bound receipt, plan, route, and state path."
        )
    return (
        "Senior Harness denied root implementation: this parallel-required root may coordinate, "
        "read, dispatch, wait, and verify, but every mutation must be owned by a bounded leaf or integration worker."
    )


def _unsigned_dispatch(payload: dict[str, Any], project_root: Path, receipt: dict[str, Any]) -> bool:
    return _is_parallel_dispatch_tool(payload) and not _has_signed_dispatch_admission(
        payload, project_root, receipt
    )


def _active_context(contract: dict[str, Any], drift: tuple[str, ...], recovered: bool) -> str:
    drift_context = (
        " Senior Harness control-code drift detected: " + "; ".join(drift)
        + ". Delivery may continue under normal host and repository policy, but this startup receipt cannot be reused as fresh control-code evidence."
        if drift else ""
    )
    action = "recovered pending objective and established" if recovered else "objective"
    return (
        f"Senior Harness {action} lock: {contract['literal_objective']!r}."
        f"{_parallel_dispatch_context(contract)} Startup admission does not authorize this tool; "
        "normal host and repository policy still decide it. This hook covers mediated local tools "
        f"only; hosted or specialized bypasses are not claimed.{drift_context}"
    )


def _tool_policy_response(
    payload: dict[str, Any], project_root: Path, receipt: dict[str, Any],
    interaction: Any, drift: tuple[str, ...], recovery_safe: bool, recovered: bool,
) -> dict[str, Any]:
    if _unsigned_dispatch(payload, project_root, receipt):
        return _hook_output(
            "PreToolUse",
            "Senior Harness denied dispatch: no verified signed dispatcher is installed.",
            deny=True,
        )
    grill_control = (
        interaction in GRILL_INTERACTIONS and _tool_is_grill_driver(payload, receipt)
    )
    if interaction in GRILL_INTERACTIONS and not (
        recovery_safe or grill_control
    ):
        return _hook_output(
            "PreToolUse",
            "Senior Harness denied the tool: Grill-Me permits evidence discovery and its control-state driver only until shared understanding is explicitly confirmed.",
            deny=True,
        )
    denial = _parallel_denial(
        payload, project_root, receipt, recovery_safe or grill_control
    )
    if denial:
        return _hook_output("PreToolUse", denial, deny=True)
    return _hook_output(
        "PreToolUse", _active_context(receipt["setup_contract"], drift, recovered)
    )


def handle_pretool(
    payload: dict[str, Any], *, project_root: Path, surface: str,
    session_id: str, state_path: Path, pending_path: Path,
    roots: Iterable[str | Path] | None,
) -> dict[str, Any]:
    recovery_safe = _tool_is_recovery_safe(payload)
    with _state_lock(_session_lock_path(session_id)):
        return _handle_pretool_locked(
            payload, project_root=project_root, surface=surface,
            session_id=session_id, state_path=state_path,
            pending_path=pending_path, roots=roots, recovery_safe=recovery_safe,
        )


def _handle_pretool_locked(
    payload: dict[str, Any], *, project_root: Path, surface: str,
    session_id: str, state_path: Path, pending_path: Path,
    roots: Iterable[str | Path] | None, recovery_safe: bool,
) -> dict[str, Any]:
    try:
        recovered, admission_error = _recover_pending(
            pending_path=pending_path, state_path=state_path, session_id=session_id,
            surface=surface, project_root=project_root, roots=roots,
        )
    except SetupError as exc:
        return _hook_output("PreToolUse", _pending_quarantine_reason(exc), deny=True)
    if not state_path.is_file():
        return _missing_state_response(recovery_safe, admission_error)
    try:
        receipt, interaction, drift = _active_tool_state(state_path, project_root)
    except (KeyError, SetupError) as exc:
        return _invalid_state_response(exc, recovery_safe)
    return _tool_policy_response(
        payload, project_root, receipt, interaction, drift, recovery_safe, recovered
    )
