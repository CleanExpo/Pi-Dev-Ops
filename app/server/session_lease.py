"""
session_lease.py — machine ownership so a session survives its machine.

Two separate defects made `status='interrupted'` rows unsafe to recover:

1. **No owner.** Every replica that boots calls
   `supabase_log.fetch_interrupted_sessions()` and got the *same* rows back, so
   three machines resumed one build three times. `mesh_work_claims` already
   solved the identical problem for Linear tickets with the
   `mesh_work_claims_one_open` partial unique index; the `sessions` half of it
   is a `claimed_by` / `lease_expires_at` pair won by a conditional PATCH
   (`supabase_log.claim_interrupted_session`).
2. **Incomplete checkpoint.** A checkpoint could not actually resume anywhere
   else: `workspace` is a machine-local path and the writer dropped most of the
   fields `session_phases.run_build()` reads after a resume.
   `checkpoint_payload()` is the complete set, plus the `host` that tells the
   recovering machine whether that `workspace` path means anything to it.

These helpers live here rather than in `supabase_log.py` because that module is
already over the 300-line ceiling and baselined in
`.github/file-length.baseline.txt` — a baselined file that grows fails CI.

Re-derive the resume path's use of `workspace`:

    grep -n "session.workspace" app/server/session_phases.py
"""
from __future__ import annotations

import json
import logging
import os
import socket
from datetime import datetime, timedelta, timezone
from typing import Any

log = logging.getLogger("pi-ceo.session_lease")

# `checkpoint` is a JSONB column rewritten on *every* phase transition, and
# three of the fields below are unbounded by construction: `evaluator_findings`
# grows per persona per retry, `modified_files` per git diff, `plan` per planner
# run. Uncapped, a long build's checkpoint grows without limit and every later
# checkpoint re-uploads the whole thing. These caps keep the row a resumable
# summary rather than an archive — the authoritative copies stay on disk.
_MAX_ITEMS = 200
_MAX_CHARS = 20_000

# Fields carried verbatim (JSON-safe scalars/containers) from session → checkpoint.
_PLAIN_FIELDS = (
    "linear_issue_id",
    "parent_session_id",
    "complexity_tier",
    "shared_workspace",
)


def local_host() -> str:
    """Short hostname of the machine running this process.

    Used as both the checkpoint's `host` and the lease's `claimed_by`. It must
    be per-*container*, not a stable fleet label: on Railway every deploy is a
    fresh container with an empty disk, so a redeploy has to read as "different
    machine" and re-clone rather than resume into a `workspace` path that no
    longer exists.
    """
    try:
        return socket.gethostname().split(".")[0] or "unknown-host"
    except Exception:  # noqa: BLE001 — hostname lookup must never break a write
        return "unknown-host"


def is_cloud() -> bool:
    """True on Railway / Render / Fly. Mirrors `app_factory._IS_CLOUD`."""
    return bool(
        os.environ.get("RAILWAY_ENVIRONMENT")
        or os.environ.get("RENDER")
        or os.environ.get("FLY_APP_NAME")
    )


def claim_machine() -> str:
    """Fleet-registry name for this worker — the `mesh_work_claims.machine` value.

    Cloud replicas deliberately collapse to one label. `mesh_machines.host` is a
    primary key the heartbeat daemon keeps one row per *physical* node in, and
    `mesh_work_claims.machine` is a foreign key onto it; a per-deploy Railway
    container id would leave a new dead `mesh_machines` row behind on every
    redeploy that no heartbeat ever refreshes.
    """
    return "railway" if is_cloud() else local_host()


def _cap_list(value: Any) -> list:
    """First `_MAX_ITEMS` entries of a list-ish value; `[]` for anything else."""
    if not isinstance(value, list):
        return []
    return value[:_MAX_ITEMS]


def _cap_text(value: Any) -> str:
    """String truncated to `_MAX_CHARS`; `""` for anything else."""
    if not isinstance(value, str):
        return ""
    return value[:_MAX_CHARS]


def _jsonable(value: Any) -> Any:
    """`value` if it round-trips through JSON, else its `vars()`, else None.

    `session.budget` is a live BudgetTracker instance, not data. Serialising the
    object raises inside the checkpoint writer, which is fire-and-forget — so
    the failure would be silent and the *whole* checkpoint would be lost, not
    just that one field. A dataclass degrades to its attribute dict; anything
    still unserialisable is dropped rather than allowed to poison the row.
    """
    if value is None:
        return None
    try:
        json.dumps(value)
        return value
    except Exception:  # noqa: BLE001
        pass
    try:
        as_dict = vars(value)
        json.dumps(as_dict)
        return as_dict
    except Exception:  # noqa: BLE001
        return None


def checkpoint_payload(session: Any) -> dict[str, Any]:
    """Build the full `sessions.checkpoint` JSONB body for one session.

    Everything `session_phases.run_build()` needs to pick a build back up on a
    different machine. `host` is the machine that wrote it —
    `session_model.recover_interrupted_sessions_from_supabase()` compares it
    against `local_host()` to decide whether `workspace` is a real directory
    here or a path from someone else's disk.
    """
    payload: dict[str, Any] = {
        "host":                local_host(),
        "last_completed_phase": getattr(session, "last_completed_phase", "") or "",
        "retry_count":         int(getattr(session, "retry_count", 0) or 0),
        "evaluator_status":    getattr(session, "evaluator_status", "pending") or "pending",
        "evaluator_score":     getattr(session, "evaluator_score", None),
        "evaluator_model":     getattr(session, "evaluator_model", "") or "",
        "evaluator_consensus": getattr(session, "evaluator_consensus", "") or "",
        "workspace":           getattr(session, "workspace", "") or "",
        "error":               getattr(session, "error", "") or "",
        "output_line_count":   len(getattr(session, "output_lines", []) or []),
        "plan":                _cap_text(getattr(session, "plan", "")),
        "modified_files":      _cap_list(getattr(session, "modified_files", [])),
        "evaluator_findings":  _cap_list(getattr(session, "evaluator_findings", [])),
        "repo_context":        _jsonable(getattr(session, "repo_context", None)),
        "scope":               _jsonable(getattr(session, "scope", None)),
        "budget":              _jsonable(getattr(session, "budget", None)),
        "budget_params":       _jsonable(getattr(session, "budget_params", None)),
        "phase_metrics":       _jsonable(getattr(session, "phase_metrics", None)),
        "plan_discovery_meta": _jsonable(getattr(session, "plan_discovery_meta", None)),
    }
    for name in _PLAIN_FIELDS:
        payload[name] = _jsonable(getattr(session, name, None))
    return payload


DEFAULT_LEASE_MINUTES = 10


def lease_deadline(minutes: int = DEFAULT_LEASE_MINUTES) -> str:
    """UTC ISO timestamp `minutes` into the future — a lease's expiry."""
    return (
        datetime.now(timezone.utc) + timedelta(minutes=int(minutes))
    ).isoformat(timespec="seconds")


def claim_interrupted_session(
    session_id: str,
    host: str,
    lease_minutes: int = DEFAULT_LEASE_MINUTES,
) -> bool:
    """Take exclusive ownership of one interrupted session. True ⇔ this caller won.

    A single conditional PATCH does the whole thing: the filter demands the row
    is still `interrupted` AND (unowned OR its lease has already expired), so
    two replicas issuing it concurrently are serialised by Postgres row locking
    and the loser's filter no longer matches by the time it is evaluated.
    `Prefer: return=representation` makes the outcome readable — exactly one row
    back means this caller flipped it, zero means someone else got there first.
    A read-then-write would race in the gap between the two statements; there is
    no gap here, which is the entire point.

    Returns True when Supabase is unconfigured: there is then no shared table to
    contend on (`fetch_interrupted_sessions` cannot return rows either), so
    failing closed would only stall local runs, never prevent a double-resume.
    """
    if not session_id or not host:
        return False
    from . import supabase_log  # noqa: PLC0415 — avoid an import cycle at module load

    if not all(supabase_log._cfg()):
        return True
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    query = (
        f"sessions?id=eq.{supabase_log._q(session_id)}&status=eq.interrupted"
        f"&or=(claimed_by.is.null,lease_expires_at.lt.{supabase_log._q(now_iso)})"
    )
    body = {"claimed_by": host, "lease_expires_at": lease_deadline(lease_minutes)}
    status, rows = supabase_log._request("PATCH", query, body, "return=representation")
    won = supabase_log._ok(status) and isinstance(rows, list) and len(rows) == 1
    if not won:
        log.info("session lease lost for %s (host=%s, http=%s)", session_id, host, status)
    return won


def claim_linear_ticket(linear_id: str) -> bool:
    """Take fleet-wide ownership of one Linear ticket, or return False.

    One INSERT into `mesh_work_claims`; the `mesh_work_claims_one_open` partial
    unique index rejects a racing second claim with HTTP 409. This deliberately
    reuses the mesh's lock instead of adding a second one, so the autonomy
    poller, the dispatcher and a runner's `claim/self` all contend on the same
    row rather than each believing they own the ticket.

    The `mesh_machines` upsert is not optional: `mesh_work_claims.machine` is a
    foreign key onto `mesh_machines.host`, and PostgREST reports a violated FK
    as 409 — indistinguishable from "already claimed". Without the upsert, a
    host with no heartbeat daemon would silently never claim anything.

    Returns True when Supabase is unconfigured: there is no shared claim table
    to contend on, so gating local/offline work on it would be a fail-closed
    stall, not a lock.
    """
    if not linear_id:
        return False
    from . import supabase_log  # noqa: PLC0415 — avoid an import cycle at module load

    if not all(supabase_log._cfg()):
        log.debug("mesh claim skipped for %s — Supabase not configured", linear_id)
        return True
    host = claim_machine()
    supabase_log._upsert("mesh_machines", {"host": host, "status": "online"})
    ok = supabase_log._insert(
        "mesh_work_claims",
        {"linear_id": linear_id, "machine": host, "state": "claimed"},
    )
    if not ok:
        log.info("mesh claim lost for %s (machine=%s) — another worker owns it", linear_id, host)
    return ok
