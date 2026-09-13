"""Build a mesh_ships insert row (RA-7377).

GET /api/mesh/fleet already reads this table. Nothing wrote it. This module
is the single row builder: validate the payload, stamp shipped_at, return
the dict the route POSTs through the existing service-role path.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

_SHA = re.compile(r"^[0-9a-f]{7,40}$")
MAX_MACHINE = 128
MAX_REPO = 256
MAX_BRANCH = 256
MAX_SUBJECT = 512
MAX_FILES = 100_000


class ShipRejected(ValueError):
    """Caller-visible validation failure — the route maps this to HTTP 422."""


def _clip(value: Any, name: str, max_len: int, required: bool) -> str | None:
    """Strip and bound a text field. Rejects empties when required, and controls."""
    if value is None:
        if required:
            raise ShipRejected(f"{name} is required")
        return None
    text = str(value).strip()
    if not text:
        if required:
            raise ShipRejected(f"{name} is required")
        return None
    if any(ord(ch) < 32 for ch in text):
        raise ShipRejected(f"{name} contains control characters")
    if len(text) > max_len:
        raise ShipRejected(f"{name} exceeds {max_len} characters")
    return text


def _files_changed(value: Any) -> int:
    """Coerce files_changed to a non-negative int. None becomes 0."""
    if value is None:
        return 0
    try:
        count = int(value)
    except (TypeError, ValueError) as exc:
        raise ShipRejected("files_changed must be an integer") from exc
    if count < 0 or count > MAX_FILES:
        raise ShipRejected(f"files_changed must be between 0 and {MAX_FILES}")
    return count


def _sha(value: Any) -> str | None:
    """Optional git object name: 7-40 hex chars, stored lowercase."""
    text = _clip(value, "sha", 40, required=False)
    if text is None:
        return None
    lowered = text.lower()
    if not _SHA.fullmatch(lowered):
        raise ShipRejected("sha must be a 7-40 character hex git object")
    return lowered


def build_row(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a mesh_ships insert row, or raise ShipRejected.

    shipped_at is stamped here so a client clock cannot back-date the feed.
    """
    machine = _clip(payload.get("machine"), "machine", MAX_MACHINE, True)
    repo = _clip(payload.get("repo"), "repo", MAX_REPO, True)
    return {
        "machine": machine,
        "repo": repo,
        "branch": _clip(payload.get("branch"), "branch", MAX_BRANCH, False),
        "sha": _sha(payload.get("sha")),
        "subject": _clip(payload.get("subject"), "subject", MAX_SUBJECT, False),
        "files_changed": _files_changed(payload.get("files_changed")),
        "shipped_at": datetime.now(timezone.utc).isoformat(),
    }
