"""mesh_priority.py — Linear priority to a claim-ordering sort key.

Extracted from routes/mesh.py rather than grown inside it: that file is
grandfathered over the 300-line ceiling, and CLAUDE.md's size ratchet says to
extract when you touch one, never to raise its baseline to get green.

Deliberately imports nothing from this package. mesh_dispatch_service defers its
`from .routes import mesh` to call time to avoid a cycle, so a helper both of
them may want has to stay free of package imports to be safe to import at module
level from either side.
"""
from __future__ import annotations

from typing import Any


def priority_rank(priority: Any) -> int:
    """Linear priority → sort key (lower = claimed first). 1=Urgent .. 4=Low;
    0/None ("No priority") sorts last so real priorities win."""
    try:
        p = int(priority)
    except (TypeError, ValueError):
        return 99
    return p if p > 0 else 99
