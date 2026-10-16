"""Hermes gateway liveness from the mesh heartbeat (Mission Control).

Hermes runs on the Mac mini, not on the Railway host that serves
/api/health/full, so a host-local heartbeat file can never be observed in
production. mesh/heartbeat.py on the Mac reports the gateway process as a
`hermes-gateway` mesh_agents row; this reads the freshest one.
"""
from __future__ import annotations

import asyncio
import datetime
import time
import urllib.parse
from typing import Any

from app.server import supabase_log

# Below health_full's 2 s per-component deadline, so a slow read is reported
# here as not observed instead of being cancelled into a red "timeout".
_READ_TIMEOUT_S = 1.5
# Heartbeats run every 20 s. A gateway row more than this behind its machine's
# last_seen was missing from several consecutive successful heartbeats.
_LAG_S = 90


async def observe_hermes_gateway() -> dict[str, Any]:
    """Run the mesh read; any failure to read is "not observed", never "down"."""
    try:
        return await asyncio.wait_for(asyncio.to_thread(hermes_gateway_from_mesh), _READ_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001 — every read failure maps to one contract
        return {"ok": False, "observed": False, "status": "not_observed",
                "error": f"mesh_agents read failed ({type(exc).__name__})"}


def _get(path: str) -> list[dict] | None:
    """One PostgREST read; None when it failed (never an empty list on failure)."""
    status, rows = supabase_log._request("GET", path, None, "")  # type: ignore[attr-defined]
    return rows if status == 200 and isinstance(rows, list) else None


def hermes_gateway_from_mesh() -> dict[str, Any]:
    """Freshest mesh_agents row for the Mac's Hermes gateway (mesh/heartbeat.py).

    A failed read is reported as not observed with an error, never as an
    empty fleet: "the read broke" and "no gateway" must stay distinguishable.
    The row alone cannot prove liveness: if the server's idle reconciliation
    failed, a dead gateway's row stays "working" (review P1). Every successful
    heartbeat restamps both the machine and each reported agent, so a row that
    lags its machine's last_seen was left out of recent heartbeats: down.
    """
    rows = _get("mesh_agents?runtime=eq.hermes-gateway"
                "&order=updated_at.desc&limit=1&select=machine,state,updated_at")
    if rows is None:
        return {"ok": False, "observed": False, "status": "not_observed", "error": "mesh_agents read failed"}
    if not rows:
        return {"ok": False, "observed": False, "status": "not_observed",
                "note": "no_hermes_gateway_row_in_mesh_heartbeat"}
    row = rows[0]
    machine = row.get("machine")
    machines = _get(f"mesh_machines?host=eq.{urllib.parse.quote(str(machine))}&select=last_seen")
    if machines is None:
        return {"ok": False, "observed": False, "status": "not_observed", "error": "mesh_machines read failed"}
    if not machines:
        return {"ok": False, "observed": False, "status": "not_observed", "note": f"no mesh_machines row for {machine}"}
    seen = datetime.datetime.fromisoformat(str(row.get("updated_at"))).timestamp()
    beat = datetime.datetime.fromisoformat(str(machines[0].get("last_seen"))).timestamp()
    base = {"observed": True, "machine": machine, "last_seen": _iso(seen)}
    if row.get("state") != "working" or beat - seen > _LAG_S:
        return {**base, "ok": False, "status": "down", "source": "mesh_heartbeat_process_absent"}
    live = time.time() - seen < 5 * 60
    return {**base, "ok": live, "status": "live" if live else "stale", "source": "mesh_heartbeat_process_seen"}


def _iso(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts, tz=datetime.UTC).isoformat()
