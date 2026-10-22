"""Lifecycle hook routing for the Senior Harness startup boundary."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from setup_common import SetupError, _hook_output
from setup_pretool import handle_pretool
from setup_prompt import handle_prompt
from setup_repository import _git
from setup_state import _pending_state_path, _session_lock_path, _state_lock, _state_path


# Cursor runs the hooks in .claude/settings.json but sends its own payload:
# camelCase event names, no cwd (or "") with the checkout in workspace_roots,
# and session_id documented only for session events (conversation_id always).
CURSOR_EVENTS = {
    "sessionStart": "SessionStart",
    "beforeSubmitPrompt": "UserPromptSubmit",
    "preToolUse": "PreToolUse",
}


def _normalise_cursor_payload(payload: Any) -> Any:
    """Map a Cursor-originated payload onto the Claude hook contract, or leave it."""
    if not isinstance(payload, dict) or "cursor_version" not in payload:
        return payload
    normalised = dict(payload)
    observed = payload.get("hook_event_name")
    if observed in CURSOR_EVENTS:
        normalised["hook_event_name"] = CURSOR_EVENTS[observed]
    if not payload.get("session_id") and isinstance(payload.get("conversation_id"), str):
        normalised["session_id"] = payload["conversation_id"]
    roots = payload.get("workspace_roots")
    if not payload.get("cwd") and isinstance(roots, list) and len(roots) == 1:
        normalised["cwd"] = roots[0]
    return normalised


def _validate_hook_input(payload: Any, surface: str, event: str) -> tuple[str, str]:
    if surface not in {"codex", "claude"}:
        raise SetupError([f"hook surface is unsupported: {surface}"])
    if event not in {"SessionStart", "UserPromptSubmit", "PreToolUse"}:
        raise SetupError([f"hook event is unsupported: {event}"])
    if not isinstance(payload, dict):
        raise SetupError(["hook payload must be a JSON object"])
    observed = payload.get("hook_event_name")
    if observed and observed != event:
        raise SetupError([f"hook event mismatch: configured={event}, observed={observed}"])
    session_id = payload.get("session_id")
    cwd = payload.get("cwd")
    if not isinstance(session_id, str) or not session_id:
        raise SetupError(["hook payload is missing session_id"])
    if not isinstance(cwd, str) or not cwd:
        raise SetupError(["hook payload is missing cwd"])
    return session_id, cwd


def _handle_session_start(
    payload: dict[str, Any], state_path: Path, pending_path: Path
) -> dict[str, Any]:
    if payload.get("source") == "clear":
        state_path.unlink(missing_ok=True)
        pending_path.unlink(missing_ok=True)
        return _hook_output(
            "SessionStart",
            "Senior Harness cleared the prior objective lock, discarding both this project's "
            "startup state and any pending objective for this session. The next user prompt "
            "will become the new primary objective.",
        )
    return _hook_output(
        "SessionStart",
        "Senior Harness setup driver is active. The first user prompt will be frozen as the primary objective before mediated tools run.",
    )


def handle_hook(
    payload: dict[str, Any], *, surface: str, event: str,
    skill_search_roots: Iterable[str | Path] | None = None,
) -> dict[str, Any]:
    """Adapt one Codex/Claude lifecycle event to the portable startup contract."""
    payload = _normalise_cursor_payload(payload)
    session_id, cwd = _validate_hook_input(payload, surface, event)
    root = Path(_git(Path(cwd).resolve(), "rev-parse", "--show-toplevel").strip()).resolve()
    state_path = _state_path(root, session_id)
    pending_path = _pending_state_path(session_id)
    if event == "SessionStart":
        with _state_lock(_session_lock_path(session_id)):
            return _handle_session_start(payload, state_path, pending_path)
    if event == "UserPromptSubmit":
        return handle_prompt(
            payload, project_root=root, surface=surface, session_id=session_id,
            state_path=state_path, pending_path=pending_path, roots=skill_search_roots,
        )
    return handle_pretool(
        payload, project_root=root, surface=surface, session_id=session_id,
        state_path=state_path, pending_path=pending_path, roots=skill_search_roots,
    )
