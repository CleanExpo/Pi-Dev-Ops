"""Reconcile one machine's mesh_agents rows on each heartbeat (routes/mesh.py).

Split out of routes/mesh.py (300-line ceiling). The caller passes its own
Supabase request function so tests that stub `mesh._sb` cover this too.
"""
from __future__ import annotations

import os
import urllib.parse
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException

Sb = Callable[..., tuple[int, str]]

# How long a machine's idle agent rows are kept before the heartbeat prunes them.
MESH_AGENT_RETENTION_HOURS = max(int(os.environ.get("MESH_AGENT_RETENTION_HOURS", "24")), 1)


def prune_idle_agents(sb: Sb, host: str) -> None:
    """Drop this machine's long-idle agent rows.

    `mesh_agents` is unique on (machine, runtime, session_id) and nothing ever
    deleted from it. That was harmless while session_id was the runtime name —
    one row per runtime, upserted forever. Now the runner reports its real
    per-claim run id, so every claim would leave a permanent idle row behind.
    Rows are only removed once they have been idle past the retention window,
    so a live agent is never pruned out from under Mission Control.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=MESH_AGENT_RETENTION_HOURS)).isoformat()
    sb("DELETE",
       f"mesh_agents?machine=eq.{urllib.parse.quote(host)}&state=eq.idle"
       f"&updated_at=lt.{urllib.parse.quote(cutoff)}",
       prefer="return=minimal")


def reconcile(sb: Sb, host: str, agents: Iterable[Any]) -> None:
    """Mark all of this machine's agents idle, then upsert the live ones.

    A failed write raises 502 rather than being acknowledged as ok: an agent the
    node stopped reporting would otherwise stay "working" (hermes_mesh_health.py).
    """
    status, _ = sb("PATCH", f"mesh_agents?machine=eq.{urllib.parse.quote(host)}",
                   {"state": "idle"}, prefer="return=minimal")
    if status >= 300:
        raise HTTPException(502, f"agent idle reconciliation failed ({status})")
    prune_idle_agents(sb, host)
    for a in agents:
        row = {"machine": host, "runtime": a.runtime, "session_id": a.session_id or a.runtime,
               "repo": a.repo, "branch": a.branch, "current_task": a.current_task, "state": a.state,
               "updated_at": datetime.now(timezone.utc).isoformat()}
        # on_conflict targets the (machine, runtime, session_id) UNIQUE constraint —
        # merge-duplicates alone resolves only against the uuid PK, so every repeat
        # heartbeat 409'd instead of upserting. updated_at is stamped explicitly for
        # the same reason last_seen is: column defaults only fire on INSERT.
        status, _ = sb("POST", "mesh_agents?on_conflict=machine,runtime,session_id", row,
                       prefer="resolution=merge-duplicates,return=minimal")
        if status >= 300:
            raise HTTPException(502, f"agent upsert failed ({status})")
