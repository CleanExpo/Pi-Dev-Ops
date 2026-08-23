"""UserPromptSubmit lifecycle handler for startup objective admission."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from setup_common import GRILL_INTERACTIONS, SetupError, _hook_output, _interaction_for_objective
from setup_receipts import _check_control_bindings, admit_startup
from setup_repository import _read_adapter_receipt, _surface_capabilities, build_setup_contract
from setup_state import (
    _pending_quarantine_reason,
    _pending_reconciliation_reason,
    _read_pending_objective,
    _read_state,
    _session_lock_path,
    _state_lock,
    _write_state,
)
from setup_tools import _parallel_dispatch_context
from setup_validation import validate_startup_receipt


def _pending_for_prompt(
    path: Path, *, session_id: str, surface: str, prompt: str
) -> tuple[str, dict[str, Any] | None]:
    if not path.is_file():
        return prompt, None
    pending = _read_pending_objective(path, session_id=session_id, surface=surface)
    return pending["literal_objective"], pending


def _existing_prompt_details(state_path: Path, project_root: Path) -> tuple[Any, ...]:
    state = _read_state(state_path)
    receipt = state.get("receipt", {})
    validate_startup_receipt(
        receipt, project=project_root, verify_repository=False,
        verify_control_bindings=False,
    )
    primary = receipt["setup_contract"]["literal_objective"]
    parallel = _parallel_dispatch_context(receipt["setup_contract"])
    bindings = _check_control_bindings(receipt)
    if bindings.integrity_failures:
        raise SetupError([*bindings.integrity_failures, *bindings.drift])
    return receipt, primary, parallel, bindings.drift


def _respond_existing_prompt(
    state_path: Path, project_root: Path, pending: dict[str, Any] | None
) -> dict[str, Any]:
    try:
        receipt, primary, parallel, drift = _existing_prompt_details(state_path, project_root)
    except (KeyError, TypeError, SetupError) as exc:
        return _hook_output(
            "UserPromptSubmit",
            "Senior Harness denied the prompt: existing startup state is invalid "
            f"({exc}). The frozen objective cannot be replaced by a later prompt. "
            "Use an explicit SessionStart with source=clear to discard the invalid state before starting a new objective.",
            deny=True,
        )
    if pending is not None:
        reason = _pending_reconciliation_reason(
            primary, pending["literal_objective"],
            admission_stamp=receipt.get("admission_order_ns"),
            pending_stamp=pending.get("recorded_at_ns"),
        )
        return _hook_output("UserPromptSubmit", reason, deny=True)
    drift_context = (
        " Control-code drift is present and must be revalidated in a fresh session: "
        + "; ".join(drift) + "." if drift else ""
    )
    context = (
        f"Senior Harness primary objective remains frozen byte-for-byte: {primary!r}. "
        f"Treat this prompt as a subordinate instruction unless the user starts a new task."
        f"{parallel}{drift_context}"
    )
    return _hook_output("UserPromptSubmit", context)


def _new_contract(
    prompt: str, project_root: Path, surface: str,
    skill_search_roots: Iterable[str | Path] | None, session_id: str | None = None,
) -> dict[str, Any]:
    interaction = _interaction_for_objective(prompt)
    if interaction is None:
        raise SetupError(["UserPromptSubmit payload is missing the literal prompt"])
    return build_setup_contract(
        prompt, project_root, surface=surface, interaction=interaction,
        skill_search_roots=skill_search_roots,
        host_session_id=session_id,
        host_capabilities=_surface_capabilities(
            surface, hooks_configured=True,
            adapter_receipt=_read_adapter_receipt(surface),
        ),
    )


def _admit_prompt(
    prompt: str, project_root: Path, surface: str, state_path: Path,
    pending_path: Path, recovered: bool,
    roots: Iterable[str | Path] | None, session_id: str,
) -> dict[str, Any]:
    contract = _new_contract(prompt, project_root, surface, roots, session_id)
    receipt = admit_startup(contract)
    _write_state(state_path, {"receipt": receipt, "first_tool_admitted": False})
    pending_path.unlink(missing_ok=True)
    interaction = contract["interaction"]
    grill = (
        " Grill interaction is active: use the governed Grill session controller; project mutation and worker dispatch remain denied until its shared-understanding receipt validates."
        if interaction in GRILL_INTERACTIONS else ""
    )
    action = "recovered the pending and bound" if recovered else "froze"
    context = (
        f"Senior Harness {action} the primary objective: {prompt!r}. Load model-router and "
        f"unlazy before substantive delivery.{_parallel_dispatch_context(contract)} Startup "
        f"admission grants no mutation, business, or irreversible authority.{grill}"
    )
    return _hook_output("UserPromptSubmit", context)


def handle_prompt(
    payload: dict[str, Any], *, project_root: Path, surface: str,
    session_id: str, state_path: Path, pending_path: Path,
    roots: Iterable[str | Path] | None,
) -> dict[str, Any]:
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise SetupError(["UserPromptSubmit payload is missing the literal prompt"])
    with _state_lock(_session_lock_path(session_id)):
        try:
            prompt, pending = _pending_for_prompt(
                pending_path, session_id=session_id, surface=surface, prompt=prompt
            )
        except SetupError as exc:
            return _hook_output(
                "UserPromptSubmit", _pending_quarantine_reason(exc), deny=True
            )
        if state_path.is_file():
            return _respond_existing_prompt(state_path, project_root, pending)
        return _admit_prompt(
            prompt, project_root, surface, state_path, pending_path,
            pending is not None, roots, session_id,
        )
