"""RA-8100 delivery reconcile: read-only status tile builder (never writes, never leases)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import delivery_reconcile_store as store

STALE_AFTER_S = 45 * 60
MAX_ITEMS = 20
TOP_SEVERITIES = ("founder", "critical")
COUNTERS = (
    "missions", "refs_outside_scope", "bot_prs", "closed_unmerged", "started_without_pr",
    "completed_without_pr", "not_refreshed", "vercel_unreadable",
    "skipped_repos", "unqueryable_projects", "incomplete",
)


def _snap(state: str, errors: list[str], enabled: bool, last_tick: str | None = None) -> dict:
    return {"enabled": enabled, "state": state, "last_tick": last_tick, "complete": False,
            "counts": None, "items": [], "errors": errors}


def _parse(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except (ValueError, OverflowError):  # an instant outside years 1..9999 in UTC has no age
        return None


def _shown(state: dict[str, Any], summary: dict[str, Any]) -> list[dict[str, Any]]:
    tick = state.get("last_tick")
    ids = summary.get("not_refreshed_ids")
    stale_ids = set(ids) if isinstance(ids, list) else set()
    alerts = [a for a in state.get("alerts", {}).values() if isinstance(a, dict)]
    if summary.get("complete") is not True:  # the store drops alerts only on a complete tick
        return alerts
    return [a for a in alerts if a.get("last_seen") == tick or a.get("mission_id") in stale_ids]


def _counts(shown: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
    by_sev: dict[str, int] = {}
    by_code: dict[str, int] = {}
    for a in shown:
        sev, code = str(a.get("severity")), str(a.get("code"))
        by_sev[sev] = by_sev.get(sev, 0) + 1
        by_code[code] = by_code.get(code, 0) + 1
    return {"by_severity": by_sev, "by_code": by_code, **{k: summary.get(k) for k in COUNTERS}}


def _items(shown: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    top = [a for a in shown if a.get("severity") in TOP_SEVERITIES]
    top.sort(key=lambda a: (_parse(a.get("since")) is None, _parse(a.get("since")) or now))
    out: list[dict[str, Any]] = []
    for a in top[:MAX_ITEMS]:
        since = _parse(a.get("since"))
        age = round((now - since).total_seconds() / 3600, 1) if since else None
        out.append({"ref": a.get("ref"), "code": a.get("code"), "age_hours": age,
                    "age_source": a.get("age_source"), "owner": a.get("next_owner"),
                    "next_action": a.get("message"), "url": a.get("url")})
    return out


def build(path: str | Path, now: datetime, enabled: bool, save_ok: bool | None,
          tick_error: str | None = None) -> dict:
    """Build the tile from the state file. ``tick_error`` is the last tick's error code: a failed
    tick is reported and the tile is not complete, whatever the last saved result says."""
    failed = [tick_error] if isinstance(tick_error, str) else []
    try:
        state = store.load(path)
    except store.StoreError:
        return _snap("unreadable", ["state_unreadable", *failed], enabled)
    tick = state.get("last_tick")
    if not isinstance(tick, (int, float)) or isinstance(tick, bool):
        return _snap("never_run", failed, enabled)
    iso = datetime.fromtimestamp(tick, timezone.utc).isoformat()
    summary = state.get("summary") if isinstance(state.get("summary"), dict) else {}
    shown = _shown(state, summary)
    errors: list[str] = []
    stale = now.timestamp() - tick > STALE_AFTER_S
    if stale:
        errors.append("stale_state")
    if save_ok is False:
        errors.append("state_write_failed")
    if isinstance(summary.get("error"), str):
        errors.append(summary["error"])
    errors.extend(e for e in failed if e not in errors)
    complete = summary.get("complete") is True and not stale and save_ok is not False and not failed
    return {"enabled": enabled, "state": "stale" if stale else "ok", "last_tick": iso,
            "complete": complete, "counts": _counts(shown, summary),
            "items": _items(shown, now), "errors": errors}
