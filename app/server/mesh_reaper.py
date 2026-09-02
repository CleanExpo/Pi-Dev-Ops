"""Stale-claim reaping, split out of `routes/mesh.py` (UNI-2301, RA-7405).

The sweep releases claims stuck in claimed/working past the TTL, freeing the
`mesh_work_claims_one_open` unique index so the ticket becomes claimable again.
It is guarded by machine liveness: a claim past TTL is reaped ONLY when the
claiming machine's heartbeat is itself stale or absent, because a live
heartbeat means the runner may still be inside its up-to-3600s agent run.

WHY THE GUARD USED TO FAIL OPEN, which is the whole of RA-7405. Both reads went
through `_, body = _sb("GET", …)` and a parser that never saw the status. A
non-2xx from PostgREST therefore arrived as an empty list, so `stale_by_host`
was `{}`, so `stale_by_host.get(machine)` returned None — never False — and the
`continue` that protects a live runner never fired. Every past-TTL claim was
released and its Linear issue dragged back to Todo, precisely when the server
had no idea which machines were alive.

The trigger is not "Supabase is down": `_sb` RAISES on a transport error, so
that case already aborted safely. It is a non-2xx that returns normally — an
expired or rotated service-role key, or an RLS change, answering 401/403 with a
valid JSON error body on every read. Reproduced before the fix: with a fresh
heartbeat and a 401 on the liveness read, a live runner's claim was reaped.

Now the sweep aborts loudly instead. Not reaping is self-correcting — the next
sweep retries — while reaping a live claim destroys work and moves a ticket.

Extracted rather than fixed in place: `routes/mesh.py` sits on its 459-line
size-gate baseline, and the guards took `_reap_stale_claims` past both that and
the 40-line function limit. Every collaborator is passed in, so this module
imports nothing from the route and stays testable with no HTTP: callers hand it
their own `_sb`/`_get`, which also keeps the existing suites' monkeypatching of
`mesh._sb` working, since the reference is resolved at call time.
"""

from __future__ import annotations

import logging
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from . import mesh_fleet

log = logging.getLogger("pi-ceo.mesh.reaper")

CANDIDATES = ("mesh_work_claims?select=id,linear_id,machine,claimed_at"
              "&state=in.(claimed,working)&claimed_at=lt.{cutoff}")
LIVENESS = "mesh_fleet?select=host,is_stale"


def survey(get: Callable[[str], "tuple[int, str]"], ttl_minutes: int):
    """`(candidates, stale_by_host)`, or `(None, reason)` if either read failed.

    Returning None for the candidate list — rather than an empty one — is the
    fix. The two are indistinguishable to the caller otherwise, and treating
    "could not read" as "nothing to do" is the benign half of the same mistake
    that made the liveness half destructive.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=ttl_minutes)).isoformat()
    candidates, problem = get_rows(get, CANDIDATES.format(cutoff=urllib.parse.quote(cutoff)))
    if problem:
        return None, f"candidate read failed ({problem})"
    if not candidates:
        return [], {}
    fleet, problem = get_rows(get, LIVENESS)
    if problem:
        return None, (f"liveness read failed ({problem}) — refusing to reap "
                      f"{len(candidates)} claim(s) without knowing who is alive")
    return candidates, {m["host"]: m.get("is_stale") for m in fleet if "host" in m}


def get_rows(get, path):
    """`mesh_fleet.read`, named here so the sweep reads as one idea per line."""
    return mesh_fleet.read(get, path)


def reap(get, sb, mark_reaped, ttl_minutes: int) -> list[dict]:
    """Release stale claims whose machine is not demonstrably alive."""
    candidates, liveness = survey(get, ttl_minutes)
    if candidates is None:
        log.warning("reap: skipping sweep — %s", liveness)
        return []
    now_iso = datetime.now(timezone.utc).isoformat()
    reaped: list[dict] = []
    for c in candidates:
        machine = c.get("machine")
        if machine is not None and liveness.get(machine) is False:
            continue  # fresh heartbeat — runner may still be legitimately working
        if _release(sb, c["id"], now_iso):
            reaped.append({"linear_id": c["linear_id"], "machine": machine})
            mark_reaped(c["linear_id"])
    return reaped


def _release(sb: Callable[..., Any], claim_id: str, now_iso: str) -> bool:
    """PATCH one claim to released. False when it matched no row.

    `return=representation`: a 0-row response means a racing reap (or the runner
    itself) already flipped this claim's state — don't record a reap or fire a
    redundant Linear transition for a row we didn't touch.
    """
    status, body = sb(
        "PATCH",
        f"mesh_work_claims?id=eq.{claim_id}&state=in.(claimed,working)",
        {"state": "released", "released_at": now_iso},
        prefer="return=representation",
    )
    return status < 300 and bool(mesh_fleet.parse_rows(body)[0])
