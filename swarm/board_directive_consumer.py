"""swarm/board_directive_consumer.py — RA-1868 senior-bot directive consumer.

Senior bots tail Board directives for their target_role on each cycle.
This module owns the read-cursor + delivery semantics so each bot has
the same shape of integration:

    from . import board_directive_consumer as _dc
    new_directives = _dc.consume_for(role="CMO", state=state)
    for d in new_directives:
        # bot acts on directive (or escalates/queues per its own rules)
        ...

Cursor tracking lives in the bot's own state dict (passed in/out by the
orchestrator). The cursor is the highest session_id already consumed,
in chronological-by-filename order.

Public API:
  consume_for(role, state) -> list[Directive]
  acknowledge(role, session_id, state) -> None     # mark consumed
  pending_count_for(role) -> int                    # for 6-pager surfacing
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from . import board as _board

log = logging.getLogger("swarm.board_directive_consumer")

REPO_ROOT = Path(__file__).resolve().parents[1]


def _cursor_key(role: str) -> str:
    """State-dict key tracking already-consumed session_ids per role."""
    return f"board_dc_consumed_{role}"


def consume_for(role: str, *,
                 state: dict[str, Any] | None = None,
                 repo_root: Path | None = None,
                 limit: int = 50) -> list[_board.Directive]:
    """Return new directives for ``role`` since the bot last consumed.

    Updates ``state`` in-place to record what was just delivered, so the
    next call only returns newer directives.

    state is the orchestrator's per-bot state dict (the same one the
    senior bots already use for daily-fire tracking). It tolerates a
    None state — useful for read-only inspection.
    """
    rr = repo_root or REPO_ROOT
    all_directives = _board.get_directives_for_role(
        role, repo_root=rr, limit=limit,
    )
    if not all_directives:
        return []

    if state is None:
        return list(all_directives)

    consumed: set[str] = set(state.get(_cursor_key(role)) or [])
    new = [d for d in all_directives if d.session_id not in consumed]
    if new:
        # Update cursor immediately — caller is expected to act on the
        # returned list. If the caller crashes mid-action, those
        # directives are still marked consumed (preferable to re-firing
        # them on next cycle and double-acting).
        consumed.update(d.session_id for d in new)
        state[_cursor_key(role)] = sorted(consumed)
    return new


def acknowledge(role: str, session_id: str, *,
                 state: dict[str, Any]) -> None:
    """Force-mark a directive's session_id as consumed for ``role``.

    Useful when a directive is acted on outside the consume_for path
    (e.g. a manual founder override) and we want to suppress re-delivery.
    """
    consumed = set(state.get(_cursor_key(role)) or [])
    consumed.add(session_id)
    state[_cursor_key(role)] = sorted(consumed)


def pending_count_for(role: str, *,
                       state: dict[str, Any] | None = None,
                       repo_root: Path | None = None) -> int:
    """Number of unconsumed directives for ``role``. Used by the 6-pager."""
    rr = repo_root or REPO_ROOT
    all_directives = _board.get_directives_for_role(role, repo_root=rr)
    if state is None:
        return len(all_directives)
    consumed = set(state.get(_cursor_key(role)) or [])
    return sum(1 for d in all_directives if d.session_id not in consumed)


def all_pending_counts(*,
                        state: dict[str, Any] | None = None,
                        repo_root: Path | None = None
                        ) -> dict[str, int]:
    """Per-role pending counts across the standard senior-agent set."""
    return {
        role: pending_count_for(role, state=state, repo_root=repo_root)
        for role in ("CFO", "CMO", "CTO", "CS")
    }


__all__ = [
    "consume_for", "acknowledge",
    "pending_count_for", "all_pending_counts",
]
