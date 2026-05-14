"""Env-flag gateway: legacy sentinel-string dispatch vs bubus typed dispatch.

DORMANT — ``BUBUS_ENABLED=0`` (default) routes to legacy ``wiring.dispatch``.
``BUBUS_ENABLED=1`` (Tue 19 May 18:00 AEST+) routes to bubus per
``[[feedback-substrate-change-discipline]]`` Discipline 5.
"""
from __future__ import annotations

import os


def bubus_enabled() -> bool:
    """Check the BUBUS_ENABLED env flag at call time."""
    val = os.environ.get("BUBUS_ENABLED", "").strip().lower()
    return val in {"1", "true", "yes"}


def dispatch(strategic_ask: str):
    """Route to bubus or legacy dispatch based on env flag."""
    if bubus_enabled():
        from swarm.board.wiring import BoardDispatchEvent, build_board_bus, handle_dispatch
        bus = build_board_bus(wal_path="/tmp/board_bus.wal.jsonl")
        return handle_dispatch(BoardDispatchEvent(strategic_ask=strategic_ask), bus=bus)
    from swarm.board import wiring
    return wiring.dispatch(strategic_ask)
