"""UNI-2643 — a session cannot be complete if its push failed.

`run_build` used to ignore `push_ok` after `_phase_push`: it always called
`mark_complete`, always emitted `=== SESSION COMPLETE ===`, and always moved
Linear to In Review. The gate-row logger was the only reader of `push_ok`.

`finish_after_push` is that missing consultation. Extracted so `session_phases.py`
and `run_build` shrink rather than grow past their length baselines.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from .session_model import mark_complete, mark_terminal

SESSION_COMPLETE_MARKER = "=== SESSION COMPLETE ==="
PUSH_FAILED_REASON = "push_failed"
IN_REVIEW = "In Review"


@dataclass(frozen=True)
class PostPushEffects:
    """The five outcomes UNI-2643 binds to `push_ok`."""

    status: str
    emit_completion_marker: bool
    linear_state: Optional[str]
    shipped: bool
    reason: Optional[str]


def decide_post_push(push_ok: bool) -> PostPushEffects:
    """Map a push result onto session, Linear, gate-row, and marker effects."""
    if push_ok:
        return PostPushEffects(
            status="complete",
            emit_completion_marker=True,
            linear_state=IN_REVIEW,
            shipped=True,
            reason=None,
        )
    return PostPushEffects(
        status="failed",
        emit_completion_marker=False,
        linear_state=None,
        shipped=False,
        reason=PUSH_FAILED_REASON,
    )


def finish_after_push(
    session: Any,
    push_ok: bool,
    push_ts: float,
    *,
    emit: Callable[[Any, str, str], None],
    persist: Callable[[Any], None],
    log_ship_gate: Callable[[Any, bool, float], None],
    update_linear_state: Callable[[str, str], None],
    sync_linear_on_completion: Callable[[Any], None],
    record_outcome: Callable[[Any, bool, float], None],
) -> PostPushEffects:
    """Apply the post-push tail. `push_ok` is the only complete path."""
    effects = decide_post_push(push_ok)
    session.last_completed_phase = "push" if push_ok else "push_failed"
    session.error = effects.reason
    if effects.status == "complete":
        mark_complete(session)
    else:
        mark_terminal(session, effects.status)
    persist(session)
    log_ship_gate(session, effects.shipped, push_ts)
    issue_id = getattr(session, "linear_issue_id", None)
    if effects.linear_state and issue_id:
        emit(session, "system", f"  Updating Linear issue {issue_id} → {effects.linear_state}")
        update_linear_state(issue_id, effects.linear_state)
    if effects.emit_completion_marker:
        emit(session, "success", f"  {SESSION_COMPLETE_MARKER}")
    else:
        emit(session, "error", f"  Push failed — session not complete ({effects.reason})")
    try:
        sync_linear_on_completion(session)
    except Exception:
        pass
    try:
        record_outcome(session, effects.shipped, push_ts)
    except Exception:
        pass
    return effects
