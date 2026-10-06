"""cron_watchdog_mesh.py — alert when a fleet runner stops (RA-7910 follow-up).

The Mac mini runner was dead from 3 Oct 13:23 for days and nothing said so: its
heartbeat kept the node "online", and claim/self records no per-runner contact.
Two signals now cover it, read from the `mesh_fleet` view every watchdog cycle:

  * `runner-down`: the node's heartbeat reports its runner breadcrumb has not
    updated for 15 min (mesh/node_health.py `runner_down`).
  * silent: no heartbeat at all for 15 min (machine off, asleep or heartbeat dead).
  * `quota` (RA-7930): the node's Claude account is out of quota, so its runner
    claims nothing until the reset. The fleet view carries the status only; the
    reset time is in the node's runner log and breadcrumb `hold_reason`.

Each problem pages once per outage: Telegram through the shared edge-triggered
sender, and a red Linear ticket (so the alert exists even with Telegram switched
off). Recovery clears it. A fleet that cannot be read is itself a problem, never
"all healthy".
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

SILENT_S = 900
FLEET_PATH = "mesh_fleet?select=host,status,last_seen&order=host"
_filed: set[str] = set()  # problems already ticketed this outage (per process)
_active: set[str] = set()  # problems seen last cycle, so recovery is announced


def _age_s(last_seen: object, now: float) -> float | None:
    try:
        ts = datetime.fromisoformat(str(last_seen).replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return now - ts.timestamp()


def problems(rows: list[dict], reason: str | None, now: float) -> dict[str, str]:
    """`{key: message}` for every node that needs a human. Pure."""
    if reason:
        return {"fleet-read": f"Mesh watchdog could not read the fleet ({reason}); runner state unknown."}
    out: dict[str, str] = {}
    for row in rows:
        host = str(row.get("host") or "?")
        age = _age_s(row.get("last_seen"), now)
        if age is None or age > SILENT_S:
            mins = "unknown" if age is None else f"{int(age // 60)} min"
            out[f"silent:{host}"] = f"{host}: no heartbeat for {mins}. Machine off, asleep or heartbeat stopped."
        elif row.get("status") == "runner-down":
            out[f"runner-down:{host}"] = (f"{host}: mesh runner has not polled for 15+ min "
                                          "(heartbeat is alive). Restart it with mesh/bootstrap.sh.")
        elif row.get("status") == "quota":
            out[f"quota:{host}"] = (f"{host}: Claude quota exhausted; its mesh runner claims nothing "
                                    "until the reset (time in the runner log hold_reason), then re-runs preflight.")
    return out


def _ticket(key: str, message: str, log) -> None:
    try:
        from .red_signals import upsert_red_linear_ticket  # noqa: PLC0415
        if upsert_red_linear_ticket(f"[RED] mesh runner: {key}", message,
                                    owner="Senior PM", founder_only=False, log=log):
            _filed.add(key)
    except Exception as exc:  # noqa: BLE001  (retried next cycle: the key stays unfiled)
        log.warning("mesh runner watchdog: ticket failed (%s)", exc)


def _telegram(key: str, message: str, log, severity: str = "high") -> None:
    """Edge-triggered: the same key pages again only after its message changes,
    which the recovery message does, so a second outage pages too."""
    try:
        from swarm.telegram_alerts import send  # noqa: PLC0415
        send(message, severity=severity, bot_name="Margot", dedup_key=f"mesh-runner:{key}")
    except Exception as exc:  # noqa: BLE001
        log.warning("mesh runner watchdog: telegram send failed (%s)", exc)


def run(fetch: Callable[[str], "tuple[int, str]"], now: float, log) -> dict[str, str]:
    """One cycle: read, page new problems, forget recovered ones. Returns the problems."""
    from . import mesh_fleet  # noqa: PLC0415
    try:
        rows, reason = mesh_fleet.read(fetch, FLEET_PATH)
    except Exception as exc:  # noqa: BLE001  (_sb raises on a transport error)
        rows, reason = [], type(exc).__name__
    found = problems(rows, reason, now)
    for key, message in found.items():
        _telegram(key, message, log)
        if key not in _filed:
            _ticket(key, message, log)
    for key in _active - set(found):
        _telegram(key, f"Recovered: {key}", log, severity="info")
    _filed.intersection_update(found)
    _active.clear()
    _active.update(found)
    return found


async def _watchdog_mesh_runners(log) -> None:
    import time  # noqa: PLC0415
    from .routes import mesh as _mesh  # noqa: PLC0415
    found = run(_mesh._get, time.time(), log)
    if found:
        log.warning("mesh runner watchdog: %s", "; ".join(sorted(found)))
