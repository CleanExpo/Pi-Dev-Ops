"""Lifecycle hook routing for the Senior Harness startup boundary."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Iterable

from setup_common import GitProbeError, SetupError, _hook_output
from setup_launch import clear_launch_root, launch_root_state
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
        clear_launch_root(payload["session_id"])
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


def _git_root(cwd: str) -> Path:
    return Path(_git(Path(cwd).resolve(), "rev-parse", "--show-toplevel").strip()).resolve()


def _inside_a_repository(cwd: str) -> bool:
    """True when the cwd or any parent holds a `.git`, whether git can use it or not.

    A probe that fails there (ownership refusal, broken gitdir, timeout) is a
    repository whose own rules are unknown, so it must keep the original deny.
    """
    path = Path(cwd).resolve()
    return any(os.path.lexists(parent / ".git") for parent in (path, *path.parents))


def _pretool_root(
    cwd: str, session_id: str, surface: str
) -> tuple[Path, Path, str | None]:
    """Resolve the root whose receipt governs this tool call.

    The cwd's own root wins whenever it holds state. Only when it holds none, or
    the cwd is in no repository at all, does the sealed launch-root record get a
    say; with no record the original outcome (missing-state deny, or
    GitProbeError) stands. The third value is the governing record's seal, or
    None when the cwd's own root governs.
    """
    try:
        root = _git_root(cwd)
    except GitProbeError:
        fallback = None if _inside_a_repository(cwd) else launch_root_state(
            session_id, surface
        )
        if fallback is None:
            raise
        return fallback
    state_path = _state_path(root, session_id)
    if state_path.is_file():
        return root, state_path, None
    return launch_root_state(session_id, surface) or (root, state_path, None)


def _still_routed(
    cwd: str, session_id: str, surface: str, routed: tuple[Path, Path, str | None]
) -> Callable[[], bool]:
    """Re-run the whole routing decision under the lock; it must not have changed.

    A clear, a new receipt for the cwd's own root, or a replaced launch record
    (even one naming the same root) landing between the first lookup and the
    lock all change the answer, and the call is then denied rather than run
    under the stale fallback.
    """
    return lambda: _pretool_root(cwd, session_id, surface) == routed


def _note_fallback(response: dict[str, Any], root: Path) -> dict[str, Any]:
    output = response.get("hookSpecificOutput", {})
    if isinstance(output.get("additionalContext"), str):
        output["additionalContext"] += (
            " The current cwd has no receipt of its own, so this call is governed by "
            f"the session's launch-root receipt at {root}."
        )
    return response


def handle_hook(
    payload: dict[str, Any], *, surface: str, event: str,
    skill_search_roots: Iterable[str | Path] | None = None,
) -> dict[str, Any]:
    """Adapt one Codex/Claude lifecycle event to the portable startup contract."""
    payload = _normalise_cursor_payload(payload)
    session_id, cwd = _validate_hook_input(payload, surface, event)
    pending_path = _pending_state_path(session_id)
    if event == "PreToolUse":
        routed = _pretool_root(cwd, session_id, surface)
        root, state_path, seal = routed
        fallback = seal is not None
        response = handle_pretool(
            payload, project_root=root, surface=surface, session_id=session_id,
            state_path=state_path, pending_path=pending_path, roots=skill_search_roots,
            still_routed=_still_routed(cwd, session_id, surface, routed)
            if fallback else None,
        )
        return _note_fallback(response, root) if fallback else response
    root = _git_root(cwd)
    state_path = _state_path(root, session_id)
    if event == "SessionStart":
        with _state_lock(_session_lock_path(session_id)):
            return _handle_session_start(payload, state_path, pending_path)
    return handle_prompt(
        payload, project_root=root, surface=surface, session_id=session_id,
        state_path=state_path, pending_path=pending_path, roots=skill_search_roots,
    )
