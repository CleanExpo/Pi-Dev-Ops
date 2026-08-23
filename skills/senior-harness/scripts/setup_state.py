"""Session and pending-objective state with fail-closed recovery semantics."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from setup_common import SEAL_PREFIX, SetupError, _hook_output
from setup_receipts import _seal_key
from setup_tools import _tool_is_recovery_safe


def _state_root() -> Path:
    override = os.environ.get("SENIOR_HARNESS_STATE_DIR")
    return Path(override).resolve() if override else (
        Path.home() / ".local" / "state" / "senior-harness" / "sessions"
    )


def _session_key(session_id: str) -> str:
    if not session_id:
        raise SetupError(["hook payload has no usable session id"])
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


def _state_path(project_root: Path, session_id: str) -> Path:
    project_key = hashlib.sha256(str(project_root).encode("utf-8")).hexdigest()[:20]
    return _state_root() / project_key / f"{_session_key(session_id)}.json"


def _pending_state_path(session_id: str) -> Path:
    return _state_root() / "pending-project" / f"{_session_key(session_id)}.json"


def _write_state(path: Path, state: dict[str, Any]) -> None:
    """Atomically publish private session state with a per-call temporary file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        dir=path.parent, prefix=f"{path.name}.", suffix=".tmp"
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(state, indent=2, sort_keys=True) + "\n")
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _read_state(path: Path) -> dict[str, Any]:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SetupError([f"startup state cannot be read: {exc}"]) from exc
    if not isinstance(state, dict):
        raise SetupError(["startup state must be a JSON object"])
    return state


def _pending_objective_seal(pending: dict[str, Any]) -> str:
    unsealed = {key: value for key, value in pending.items() if key != "pending_seal"}
    payload = json.dumps(
        unsealed, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return SEAL_PREFIX + hmac.new(_seal_key(), payload, hashlib.sha256).hexdigest()


def _pending_reconciliation_reason(
    frozen: str, pending_objective: str, *, admission_stamp: Any = None,
    pending_stamp: Any = None,
) -> str:
    return (
        "Senior Harness denied the request: this project holds a frozen objective "
        f"{frozen!r} while a pending startup objective {pending_objective!r} is sealed for "
        "the same session. Their order cannot be established, so neither is discarded. "
        "Wall-clock stamps, which are NOT authoritative ordering evidence and must not be "
        f"used to decide which to keep: admission={admission_stamp!r}, "
        f"pending={pending_stamp!r}. Reconcile explicitly. The only other exit is an "
        "explicit SessionStart with source=clear, which DISCARDS BOTH records -- the frozen "
        "project objective and its receipt as well as the pending objective -- so capture "
        "anything worth keeping before running it."
    )


def _pending_quarantine_reason(exc: SetupError) -> str:
    return (
        f"Senior Harness denied the request: pending startup objective is invalid ({exc}). "
        "This session stays denied until an explicit SessionStart with source=clear; no "
        "later prompt or tool can override it. That clear DISCARDS BOTH records -- the "
        "invalid pending objective AND this project's frozen objective and receipt if it "
        "holds one -- so capture anything worth keeping before running it."
    )


def _read_pending_objective(
    path: Path, *, session_id: str, surface: str
) -> dict[str, Any]:
    try:
        pending = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SetupError([f"pending startup objective cannot be read: {exc}"]) from exc
    if not isinstance(pending, dict):
        raise SetupError(["pending startup objective must be a JSON object"])
    seal = pending.get("pending_seal")
    if not isinstance(seal, str) or not hmac.compare_digest(seal, _pending_objective_seal(pending)):
        raise SetupError(["pending startup objective seal is invalid"])
    objective = pending.get("literal_objective")
    if not isinstance(objective, str) or not objective.strip():
        raise SetupError(["pending startup objective is missing its literal prompt"])
    if pending.get("session_key") != _session_key(session_id):
        raise SetupError(["pending startup objective belongs to a different session"])
    if pending.get("surface") != surface:
        raise SetupError(["pending startup objective belongs to a different host surface"])
    return pending


def _clear_pending(event: str, path: Path) -> dict[str, Any]:
    path.unlink(missing_ok=True)
    return _hook_output(
        event,
        "Senior Harness cleared the pending objective lock. The next user prompt will become the new primary objective.",
    )


def _outside_git_tool(payload: dict[str, Any], event: str) -> dict[str, Any]:
    if _tool_is_recovery_safe(payload):
        return _hook_output(
            event,
            "Senior Harness recovery-only read outside a Git project. No startup receipt exists, so this permits exact read-only discovery only and grants no mutation, provider, worker, business, or irreversible authority.",
        )
    return _hook_output(
        event,
        "Senior Harness denied the tool outside Git: no startup receipt exists for this session.",
        deny=True,
    )


def _pending_prompt(
    payload: dict[str, Any], *, surface: str, event: str, path: Path, session_id: str
) -> dict[str, Any]:
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise SetupError(["UserPromptSubmit payload is missing the literal prompt"])
    if path.is_file():
        try:
            pending = _read_pending_objective(path, session_id=session_id, surface=surface)
        except SetupError as exc:
            return _hook_output(event, _pending_quarantine_reason(exc), deny=True)
        primary = pending["literal_objective"]
        return _hook_output(
            event,
            f"Senior Harness pending primary objective remains frozen byte-for-byte: {primary!r}. Enter a real Git checkout to bind startup admission; this pending record grants no authority.",
        )
    pending = {
        "session_key": _session_key(session_id), "literal_objective": prompt,
        "surface": surface, "recorded_at_ns": time.time_ns(),
    }
    pending["pending_seal"] = _pending_objective_seal(pending)
    _write_state(path, pending)
    return _hook_output(
        event,
        f"Senior Harness froze a pending primary objective outside Git: {prompt!r}. It will bind to the first verified Git checkout; no startup, mutation, business, or irreversible authority has been granted.",
    )


def _record_pending_objective(
    payload: dict[str, Any], *, surface: str, event: str
) -> dict[str, Any]:
    """Freeze a prompt before a checkout exists; never issue startup admission here."""
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise SetupError(["hook payload is missing session_id"])
    path = _pending_state_path(session_id)
    if event == "SessionStart" and payload.get("source") == "clear":
        return _clear_pending(event, path)
    if event == "PreToolUse":
        return _outside_git_tool(payload, event)
    if event != "UserPromptSubmit":
        return _hook_output(
            event,
            "Senior Harness global hook is inactive because this task is outside a Git project. No admission or authority claim was made.",
        )
    return _pending_prompt(
        payload, surface=surface, event=event, path=path, session_id=session_id
    )
