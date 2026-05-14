"""swarm.board — Pi-CEO Board package.

Two cooperating surfaces:
  * `state`   — RA-1868 state machine (BoardBrief / queue / sessions / directives)
  * `wiring`  — dispatch kernel (Persona calls, BoardDecision, bus events)

Until PR #233 ``swarm/board.py`` was a single flat module. The .pyc source
restore (#233) shipped a package that shadowed the legacy module and left
``__init__.py`` empty, hiding the state-machine surface from every importer
(``from swarm import board as B``) — see PR #235 / Task 3 #236 CI cascade.

This module re-surfaces the state API at the package root so all historical
imports continue to work without touching call sites.
"""
from __future__ import annotations

# State machine (RA-1868) — re-export at package root.
from .state import (
    # Path constants
    MEETINGS_DIR_REL,
    PENDING_DIR_REL,
    SESSIONS_DIR_REL,
    DIRECTIVES_DIR_REL,
    CEO_BOARD_SKILL_INVOCATION,
    DEFAULT_BOARD_TIMEOUT_S,
    # Dataclasses
    BoardBrief,
    Directive,
    BoardSession,
    # Brief / parsing helpers
    assemble_brief,
    _extract_minutes_summary,
    _parse_directives,
    # SDK call (monkeypatched in tests)
    _call_ceo_board_sdk,
    # Queue + lifecycle
    request_deliberation,
    deliberate,
    process_pending,
    get_pending,
    get_completed,
    get_directives_for_role,
)

__all__ = [
    "MEETINGS_DIR_REL",
    "PENDING_DIR_REL",
    "SESSIONS_DIR_REL",
    "DIRECTIVES_DIR_REL",
    "CEO_BOARD_SKILL_INVOCATION",
    "DEFAULT_BOARD_TIMEOUT_S",
    "BoardBrief",
    "Directive",
    "BoardSession",
    "assemble_brief",
    "_extract_minutes_summary",
    "_parse_directives",
    "_call_ceo_board_sdk",
    "request_deliberation",
    "deliberate",
    "process_pending",
    "get_pending",
    "get_completed",
    "get_directives_for_role",
]
