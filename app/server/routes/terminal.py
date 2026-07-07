"""Terminal Orchestrator read API — the pane-UI backend (RA-7012).

Exposes the read-only observer verbs (`list_sessions` / `status` / `tail`) over
HTTP so Mission Control can render the live fleet. Output is already secret-redacted
by the observer (single redaction pass); this route adds auth + a lines cap and does
no redaction of its own. Write verbs (`swarm.tmux_writer`) are NOT exposed here — the
UI is read-only; state changes go through the gated writer, not a dashboard fetch.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..auth import require_auth

router = APIRouter(prefix="/api/terminal", tags=["terminal"])

_MAX_TAIL_LINES = 500


@router.get("/sessions", dependencies=[Depends(require_auth)])
async def sessions() -> dict:
    """List all tmux sessions (redacted snapshot)."""
    from swarm.tmux_observer import list_sessions  # lazy: keep libtmux off the import path

    try:
        return list_sessions()
    except Exception as exc:  # noqa: BLE001 — observer failure must not 500 the dashboard
        return {"sessions": [], "error": str(exc)}


@router.get("/tail", dependencies=[Depends(require_auth)])
async def tail(
    session: str = Query(..., min_length=1, max_length=64),
    lines: int = Query(100, ge=1, le=_MAX_TAIL_LINES),
) -> dict:
    """Redacted last-N-lines capture of a session's active pane."""
    from swarm.tmux_observer import tail as _tail  # lazy import

    try:
        return _tail(session, lines=lines)
    except Exception as exc:  # noqa: BLE001
        return {"session": session, "lines": [], "error": str(exc)}
