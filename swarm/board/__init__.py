"""Compatibility package for the legacy ``swarm.board`` module plus submodules.

PR #240 adds ``swarm.board.wiring`` and related dormant typed-dispatch modules.
Keeping this directory as a package shadows the pre-existing ``swarm/board.py``
module, so load that legacy module body into this package namespace first.
"""
from __future__ import annotations

import logging as _logging
from pathlib import Path as _Path
from typing import Any as _Any

_LEGACY_BOARD_PATH = _Path(__file__).resolve().parents[1] / "board.py"
exec(compile(_LEGACY_BOARD_PATH.read_text(encoding="utf-8"), str(_LEGACY_BOARD_PATH), "exec"), globals())


def _audit(type_: str, **fields: _Any) -> None:
    """Best-effort audit emit — never raises."""
    try:
        from swarm import audit_emit  # noqa: PLC0415

        audit_emit.row(type_, "Board", **fields)
    except Exception as exc:  # noqa: BLE001
        _logging.getLogger("swarm.board").debug("board: audit_emit suppressed (%s): %s", type_, exc)
