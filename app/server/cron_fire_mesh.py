"""cron_fire_mesh.py — scheduled Nexus Mesh dispatcher tick.

The mesh shipped with a working dispatcher that nothing called: `grep -rn
"/api/mesh/dispatch"` found the endpoint and no scheduler. A fleet could be
fully online, heartbeating, and idle, because assignment only happened when a
human POSTed the endpoint by hand. This is the missing caller.

The tick itself is `mesh_dispatch_service.run_dispatch_tick` — shared with the
HTTP route, so scheduled and manual dispatch cannot drift apart.
"""
import asyncio

from .mesh_dispatch_service import dispatch_enabled, run_dispatch_tick


async def _fire_mesh_dispatch_trigger(trigger: dict, log) -> None:
    """Assign `mesh:auto` tickets to the least-loaded online machines.

    Gated on ``MESH_DISPATCH_ENABLED`` — deploying the scheduler must not, by
    itself, start handing work to machines. A disabled tick logs and returns
    rather than raising: a deliberate off switch is not a trigger failure, and
    raising here would blank ``last_fired_at`` and set off the cron watchdog.

    Runs in a worker thread: the tick is blocking urllib I/O (Supabase +
    Linear), and the cron loop is the server's event loop.
    """
    if not dispatch_enabled():
        log.info("mesh_dispatch id=%s skipped — MESH_DISPATCH_ENABLED not set", trigger["id"])
        return
    result = await asyncio.to_thread(run_dispatch_tick, trigger.get("linear_ids") or None)
    assigned = result.get("assigned") or []
    log.info(
        "mesh_dispatch id=%s assigned=%d online=%s%s",
        trigger["id"], len(assigned), result.get("online_machines") or [],
        f" reason={result['reason']}" if result.get("reason") else "",
    )
    for row in assigned:
        log.info("mesh_dispatch → %s claimed by %s", row["linear_id"], row["machine"])
