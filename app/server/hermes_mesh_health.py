"""Hermes gateway liveness from the mesh heartbeat (Mission Control).

Hermes runs on the Mac mini, not on the Railway host that serves
/api/health/full, so a host-local heartbeat file can never be observed in
production. mesh/heartbeat.py on the Mac reports the gateway process as a
`hermes-gateway` mesh_agents row; this reads the freshest one.
"""
from __future__ import annotations

import datetime
import time
from typing import Any

from app.server import supabase_log


def hermes_gateway_from_mesh() -> dict[str, Any]:
    """Freshest mesh_agents row for the Mac's Hermes gateway (mesh/heartbeat.py).

    A failed read is reported as not observed with an error, never as an
    empty fleet: "the read broke" and "no gateway" must stay distinguishable.
    """
    status, rows = supabase_log._request(  # type: ignore[attr-defined]
        "GET",
        "mesh_agents?runtime=eq.hermes-gateway"
        "&order=updated_at.desc&limit=1&select=machine,state,updated_at",
        None,
        "",
    )
    if status != 200 or not isinstance(rows, list):
        return {"ok": False, "observed": False, "status": "not_observed",
                "error": f"mesh_agents read failed (status {status})"}
    if not rows:
        return {"ok": False, "observed": False, "status": "not_observed",
                "note": "no_hermes_gateway_row_in_mesh_heartbeat"}
    row = rows[0]
    if row.get("state") != "working":
        # The Mac's heartbeat stopped reporting the process: the server marked
        # the row idle. The gateway is down, not merely unobserved.
        return {"ok": False, "observed": True, "status": "down",
                "machine": row.get("machine"), "source": "mesh_heartbeat_process_absent"}
    last_seen = datetime.datetime.fromisoformat(str(row.get("updated_at")))
    live = time.time() - last_seen.timestamp() < 5 * 60
    return {"ok": live, "observed": True, "status": "live" if live else "stale",
            "last_seen": last_seen.isoformat(), "machine": row.get("machine"),
            "source": "mesh_heartbeat_process_seen"}
