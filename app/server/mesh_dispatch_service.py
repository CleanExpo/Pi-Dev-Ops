"""mesh_dispatch_service.py — one dispatcher tick, callable without HTTP.

Spec: docs/superpowers/specs/2026-06-11-nexus-mesh-design.md (P2, "dispatcher
auto-assignment from Linear").

The mesh shipped its dispatcher as an HTTP endpoint only, and nothing ever
called it — the fleet could be fully online and still take no work, because
assignment happened only when a human POSTed `/api/mesh/dispatch`. The tick
lives here instead of in the route so the cron loop can call it in-process:
a server calling its own HTTP endpoint would need its own secret, a live URL
and a network round trip to do what is a function call.

Re-derive that the route and the cron share one implementation:

    grep -n "run_dispatch_tick" app/server/routes/mesh.py app/server/cron_fire_mesh.py

Concurrency: this is safe to run alongside a runner's `claim/self` and a
second replica's tick. Every claim is an INSERT guarded by the
`mesh_work_claims_one_open` partial unique index (mesh/schema/0001_nexus_mesh.sql),
so a racing double-claim loses with 409 and is skipped, never retried into a
duplicate.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

log = logging.getLogger("pi-ceo.mesh.dispatch")


def dispatch_enabled() -> bool:
    """Whether the scheduled dispatcher may assign work.

    Default OFF: activating the fleet changes what machines do unattended, so
    it is an explicit operator decision, not a side effect of deploying this
    module. The HTTP endpoint is unaffected — it stays available for manual
    ticks regardless.
    """
    return os.environ.get("MESH_DISPATCH_ENABLED", "0").strip().lower() in ("1", "true", "yes")


def run_dispatch_tick(linear_ids: Optional[list[str]] = None) -> dict[str, Any]:
    """Assign unclaimed work to free nodes. One tick, idempotent.

    Tickets come from the explicit `linear_ids` list, or from Linear's
    `mesh:auto` pool when it is empty. Nodes are ordered least-loaded first
    (`_online_machines`) and then filled round-robin, so a three-machine fleet
    spreads work instead of stacking it on whichever node answered first.

    Returns the assignment list plus the machines considered, so the caller
    can log what actually happened rather than "tick ran".
    """
    # Imported here, not at module scope: the route module imports this one, so
    # a module-level import back into it would be circular. By call time the
    # routes module is always loaded.
    from .routes import mesh as mesh_routes  # noqa: PLC0415

    mesh_routes._reap_sweep_best_effort()  # free dead-runner claims before assigning
    if linear_ids:
        tickets: list[dict] = [{"identifier": t} for t in linear_ids]
    else:
        data = mesh_routes._linear_graphql(mesh_routes._MESH_AUTO_QUERY)
        tickets = (data.get("issues", {}) or {}).get("nodes", []) or []

    machines = mesh_routes._online_machines()
    if not machines:
        return {"assigned": [], "online_machines": [], "reason": "no online machines"}

    open_ids = mesh_routes._open_claim_ids()
    assigned: list[dict] = []
    idx = 0
    for ticket in tickets:
        ident = ticket.get("identifier") or ticket.get("id")
        if not ident or ident in open_ids:
            continue
        host = machines[idx % len(machines)]["host"]  # least-loaded first, then round-robin
        status, _ = mesh_routes._sb(
            "POST", "mesh_work_claims",
            {"linear_id": ident, "machine": host, "state": "claimed"},
            prefer="return=minimal",
        )
        if status < 300:
            assigned.append({"linear_id": ident, "machine": host})
            open_ids.add(ident)
            idx += 1
            mesh_routes._mark_issue_in_progress(ticket)  # leave the pool — no re-claim loop
        # status 409 = already claimed by a racing dispatch/self-claim → skip silently
    return {"assigned": assigned, "online_machines": [m["host"] for m in machines]}
