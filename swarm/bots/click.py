"""
swarm/bots/click.py — RA-650-E: Click Bot.

Responsibilities:
  - Poll Pi-Dev-Ops /health endpoint every cycle (local + Railway)
  - Detect stalled build sessions (active for >90 min with no status change)
  - Monitor autonomy loop health (last_poll_at, armed state)
  - Check disk space and API key availability
  - In shadow mode: log observations, flag issues — no UI actions taken
  - In active mode (Phase 2+): kill stalled sessions, trigger restarts,
    interact with Cowork sidebar via browser automation

Shadow mode is the safe default.  Active mode requires TAO_SWARM_SHADOW=0
plus explicit board sign-off on Phase 2 activation.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

from .. import config
from ..telegram_alerts import send

log = logging.getLogger("swarm.click")

# Sessions stuck in active state longer than this are flagged as stalled.
STALL_THRESHOLD_S: int = 90 * 60  # 90 minutes


def _http_get(url: str, timeout: int = 8) -> tuple[int, dict | None]:
    """GET a URL, return (status_code, parsed_json_or_none).

    Returns (0, None) on connection error (server down / unreachable).
    """
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            try:
                return resp.status, json.loads(body)
            except Exception:
                return resp.status, None
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:
        return 0, None


def _check_local_health() -> dict:
    """Poll the local Pi-Dev-Ops /health endpoint.

    Returns a structured observation dict.
    """
    base = config.PIDEVOPS_BASE_URL.rstrip("/")
    status_code, data = _http_get(f"{base}/health")

    if status_code == 0:
        return {
            "reachable": False,
            "status": "unreachable",
            "message": f"Pi-Dev-Ops backend not reachable at {base}",
        }

    if status_code != 200 or not data:
        return {
            "reachable": True,
            "status": "degraded",
            "http_status": status_code,
            "message": f"Backend returned HTTP {status_code}",
        }

    sessions = data.get("sessions", {})
    active = sessions.get("active", 0)
    total = sessions.get("total", 0)
    max_s = sessions.get("max", 0)
    disk_gb = data.get("disk_free_gb")
    autonomy = data.get("autonomy", {})
    uptime_s = data.get("uptime_s", 0)

    observations: list[str] = []
    warnings: list[str] = []

    # Disk space
    if disk_gb is not None and disk_gb < 2.0:
        warnings.append(f"Disk space critical: {disk_gb}GB free")
    elif disk_gb is not None:
        observations.append(f"Disk: {disk_gb}GB free")

    # API keys
    if not data.get("anthropic_key"):
        warnings.append("ANTHROPIC_API_KEY not set")
    if not data.get("linear_key"):
        warnings.append("LINEAR_API_KEY not set")

    # Autonomy loop
    if not autonomy.get("armed"):
        observations.append("Autonomy loop disarmed (expected in dev)")
    else:
        secs_since = autonomy.get("seconds_since_last_poll")
        if secs_since is not None and secs_since > 600:
            warnings.append(f"Autonomy poll stale: last poll {secs_since}s ago")
        else:
            observations.append(f"Autonomy armed, last poll {secs_since}s ago")

    # Sessions
    observations.append(f"Sessions: {active} active / {total} total (max {max_s})")
    if active > 0 and max_s > 0 and (active / max_s) >= 0.8:
        warnings.append(f"Session pool near capacity: {active}/{max_s}")

    return {
        "reachable": True,
        "status": data.get("status", "ok"),
        "http_status": status_code,
        "uptime_s": uptime_s,
        "active_sessions": active,
        "total_sessions": total,
        "disk_free_gb": disk_gb,
        "autonomy_armed": autonomy.get("armed", False),
        "observations": observations,
        "warnings": warnings,
        "message": "; ".join(warnings) if warnings else "; ".join(observations[:2]),
    }


def _check_railway_health() -> dict:
    """Poll the Railway-deployed Pi-Dev-Ops /health endpoint if configured.

    Uses PIDEVOPS_RAILWAY_URL env var.  Skips gracefully if not set.
    """
    import os
    railway_url = os.environ.get("PIDEVOPS_RAILWAY_URL", "").rstrip("/")
    if not railway_url:
        return {"skipped": True, "reason": "PIDEVOPS_RAILWAY_URL not configured"}

    status_code, data = _http_get(f"{railway_url}/health")
    if status_code == 0:
        return {"reachable": False, "url": railway_url, "message": "Railway backend unreachable"}
    return {
        "reachable": True,
        "status": data.get("status", "unknown") if data else f"HTTP {status_code}",
        "url": railway_url,
        "http_status": status_code,
        "uptime_s": (data or {}).get("uptime_s"),
        "active_sessions": (data or {}).get("sessions", {}).get("active", 0),
    }


def _log_cycle(entry: dict) -> None:
    """Append a Click observation to the JSONL log."""
    log_file = config.SWARM_LOG_DIR / "click.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def run_cycle(unacked_count: int) -> dict:
    """Execute one Click observation cycle.

    Checks:
      1. Local Pi-Dev-Ops /health (reachability, sessions, disk, autonomy)
      2. Railway /health (if PIDEVOPS_RAILWAY_URL is set)

    In shadow mode: log observations, escalate warnings — no UI actions.
    In active mode (Phase 2+): kill stalled sessions, trigger restarts.

    Args:
        unacked_count: Current unacked iteration count from orchestrator.

    Returns:
        Dict with keys: local_ok, railway_ok, warnings, shadow_mode.
    """
    local = _check_local_health()
    railway = _check_railway_health()

    warnings = local.get("warnings", [])
    all_ok = local.get("reachable", False) and local.get("status") == "ok"

    result: dict = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "local": local,
        "railway": railway,
        "local_ok": all_ok,
        "warning_count": len(warnings),
        "shadow_mode": config.SHADOW_MODE,
        "summary": local.get("message", "No data"),
    }

    _log_cycle(result)

    # Escalate warnings to Telegram regardless of shadow mode
    if warnings:
        send(
            message=(
                f"<b>Click Report — Service Warnings</b>\n\n"
                + "\n".join(f"⚠️ {w}" for w in warnings)
                + f"\n\nLocal: {'✅' if local.get('reachable') else '❌'} "
                + f"Railway: {'✅' if railway.get('reachable') else ('⏭️ skipped' if railway.get('skipped') else '❌')}"
            ),
            severity="high",
            bot_name="Click",
        )

    if not local.get("reachable"):
        log.warning("Click: Pi-Dev-Ops backend unreachable at %s", config.PIDEVOPS_BASE_URL)
    else:
        log.info(
            "Click cycle: local=%s sessions=%d/%d warnings=%d",
            local.get("status", "?"),
            local.get("active_sessions", 0),
            local.get("total_sessions", 0),
            len(warnings),
        )

    return result
