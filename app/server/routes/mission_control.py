"""
mission_control.py — /api/mission-control/live aggregator for the dashboard.

Single endpoint that powers the "live autonomy" view — polled every 5s by the
React LiveActivityFeed component. Returns everything the dashboard needs in one
shape so the frontend stays dumb + fast.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends

from .. import autonomy
from ..auth import require_auth
from ..autonomy_eligibility import filter_claimable_issues, queue_snapshot_from_issues
from ..claude_session_hud import claude_session_hud as _claude_session_hud
from ..idea_pipeline import daily_snapshot as _idea_pipeline_snapshot
from ..nexus_one.status import status_payload_for_app
from .health_aggregate import _is_observed, classify
from .health_full import gather_components
from .mission_control_sessions import (
    active_sessions as _active_sessions,
    hourly_throughput_24h as _hourly_throughput_24h,
    recent_completions as _recent_completions,
)

log = logging.getLogger("pi-ceo.mission_control")
router = APIRouter(prefix="/api/mission-control", tags=["mission-control"])

_queue_cache: tuple[float, dict] | None = None
_pulse_cache: tuple[float, dict] | None = None
_queue_cache_lock = threading.Lock()
_pulse_cache_lock = threading.Lock()
_QUEUE_CACHE_SECONDS = 300
_PULSE_CACHE_SECONDS = 60


def _linear_graphql(query: str, variables: dict | None = None) -> dict:
    key = os.environ.get("LINEAR_API_KEY", "").strip()
    if not key:
        return {}
    return autonomy._gql(key, query, variables, timeout=6)


def _queue_snapshot() -> dict:
    """Displayed queue is the claimable autonomy queue (UNI-2648).

    Shape lives in queue_snapshot_from_issues — urgent/high/next_issue_*.
    The UNI-2647 contract walker follows this return; do not flatten it.
    """
    key = os.environ.get("LINEAR_API_KEY", "").strip()
    if not key:
        return queue_snapshot_from_issues([])
    registry = {p["project_id"] for p in autonomy._load_portfolio_projects()}
    issues = filter_claimable_issues(
        autonomy.fetch_todo_issues(key, fail_on_error=True),
        registered_project_ids=registry,
        priority_labels=autonomy._PRIORITY_FILTER,
    )
    return queue_snapshot_from_issues(issues)


def _pulse_status() -> dict:
    try:
        # This read parents[2] — <repo>/app — while linear_pulse writes to
        # <repo>/.harness, so the heartbeat came from a path nothing ever wrote.
        state_file = _repo_root() / ".harness" / "linear-pulse-state.json"
        state = json.loads(state_file.read_text()) if state_file.exists() else {}
    except Exception:  # noqa: BLE001
        state = {}
    pulse_id = state.get("pulse_issue_id")
    if not pulse_id:
        return {"last_at": None, "comments_today": 0, "pulse_issue_id": None}
    q = """
    query($id: String!) {
      issue(id: $id) {
        identifier
        comments(first: 50, orderBy: updatedAt) { nodes { createdAt } }
      }
    }
    """
    data = _linear_graphql(q, {"id": pulse_id})
    issue = (data or {}).get("issue") or {}
    nodes = (issue.get("comments") or {}).get("nodes") or []
    today = datetime.now(timezone.utc).date().isoformat()
    comments_today = sum(1 for n in nodes if (n.get("createdAt") or "").startswith(today))
    last_at = nodes[0].get("createdAt") if nodes else None
    return {"last_at": last_at, "comments_today": comments_today, "pulse_issue_id": issue.get("identifier") or pulse_id}


def _cached_queue_snapshot() -> dict:
    """Reuse the portfolio read across the 5-second live-view refreshes."""
    global _queue_cache
    if autonomy.linear_rate_limited():
        return queue_snapshot_from_issues([])
    if not os.environ.get("LINEAR_API_KEY", "").strip():
        return _queue_snapshot()
    with _queue_cache_lock:
        if autonomy.linear_rate_limited():
            return queue_snapshot_from_issues([])
        if _queue_cache is not None and time.monotonic() < _queue_cache[0]:
            return _queue_cache[1]
        try:
            snapshot = _queue_snapshot()
        except Exception as exc:  # noqa: BLE001 — live panel is best-effort
            log.debug("mission_control queue snapshot failed: %s", type(exc).__name__)
            return queue_snapshot_from_issues([])
        if not autonomy.linear_rate_limited():
            _queue_cache = (time.monotonic() + _QUEUE_CACHE_SECONDS, snapshot)
        return snapshot


def _cached_pulse_status() -> dict:
    global _pulse_cache
    if autonomy.linear_rate_limited():
        return {"last_at": None, "comments_today": 0, "pulse_issue_id": None}
    if not os.environ.get("LINEAR_API_KEY", "").strip():
        return _pulse_status()
    with _pulse_cache_lock:
        if autonomy.linear_rate_limited():
            return {"last_at": None, "comments_today": 0, "pulse_issue_id": None}
        if _pulse_cache is not None and time.monotonic() < _pulse_cache[0]:
            return _pulse_cache[1]
        try:
            snapshot = _pulse_status()
        except Exception as exc:  # noqa: BLE001 — live panel is best-effort
            log.debug("mission_control pulse fetch failed: %s", type(exc).__name__)
            return {"last_at": None, "comments_today": 0, "pulse_issue_id": None}
        if not autonomy.linear_rate_limited():
            _pulse_cache = (time.monotonic() + _PULSE_CACHE_SECONDS, snapshot)
        return snapshot


_OBSERVABILITY_ACTIONS = {
    "schema_drift_db": {
        "owner": "Deploy/infra operator",
        "severity": "medium",
        "next_action": "Set SUPABASE_DB_URL on the Railway Pi-Dev-Ops service to the schema_drift_ro session-pooler connection string (docs/schema-drift-db.md). Never paste the value into chat or logs.",
        "evidence_required": ["/api/health/full components.schema_drift_db has observed=true and ok=true", "Schema Drift workflow run on main concludes success"],
    },
    "railway_deploy_config": {
        "owner": "Deploy/infra operator",
        "severity": "high",
        "next_action": "Restore Railway's repo-backed deploy contract: Dockerfile builder, guarded model-fabric bootstrap, and /health healthcheck.",
        "evidence_required": ["railway.toml contract check passes", "Railway latest deployment manifest matches Dockerfile + guarded bootstrap + /health"],
    },
    "hermes_gateway": {"owner": "Hermes/Codex operator", "severity": "high", "next_action": "Start or repair the Mac Mini Hermes heartbeat writer so .harness/hermes/heartbeat.jsonl updates within five minutes.", "evidence_required": ["fresh heartbeat.jsonl row", "Mission Control fully_observed recalculation"]},
    "margot_route": {"owner": "Margot operator", "severity": "medium", "next_action": "Run a Margot turn or sync conversation evidence so .harness/margot/conversations has a fresh record.", "evidence_required": ["fresh Margot conversation JSONL", "last_turn_at within 24h"]},
    "openrouter": {"owner": "LLM routing steward", "severity": "medium", "next_action": "Generate a low-cost model-router heartbeat or restore the llm-cost log writer.", "evidence_required": ["fresh .harness/llm-cost.jsonl row"]},
    "supabase": {"owner": "Data/CRM operator", "severity": "high", "next_action": "Run supabase_health.health_check and repair whatever it reports so Mission Control proves Supabase reads are observable.", "evidence_required": ["supabase_health.health_check returns observed=true and ok=true", "integration health check evidence"]},
    "telegram_polling": {"owner": "Mobile/operator comms", "severity": "high", "next_action": "Start or repair Telegram polling heartbeat so .harness/telegram-poll-heartbeat updates within two minutes.", "evidence_required": ["fresh telegram-poll-heartbeat mtime", "operator alert route verified"]},
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _railway_deploy_config_component() -> dict:
    path = _repo_root() / "railway.toml"
    if not path.exists():
        return {"ok": False, "observed": True, "status": "missing", "error": "railway.toml is missing"}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return {"ok": False, "observed": True, "status": "invalid", "error": f"railway.toml unreadable: {exc}"}

    build = data.get("build") if isinstance(data.get("build"), dict) else {}
    deploy = data.get("deploy") if isinstance(data.get("deploy"), dict) else {}
    expected = {"builder": "DOCKERFILE", "dockerfilePath": "Dockerfile", "healthcheckPath": "/health", "healthcheckTimeout": 30}
    mismatches = {
        key: {"expected": value, "actual": (build if key in build else deploy).get(key)}
        for key, value in expected.items()
        if (build if key in build else deploy).get(key) != value
    }
    start = str(deploy.get("startCommand") or "")
    accepted_start_commands = {
        "python scripts/runtime_model_guard.py",
        "uvicorn app.server.main:app --host 0.0.0.0 --port 8080 --workers 1",
    }
    if start not in accepted_start_commands:
        mismatches["startCommand"] = {
            "expected": "python scripts/runtime_model_guard.py (preferred) or canonical uvicorn fallback",
            "actual": start or None,
        }
    return {
        "ok": not mismatches,
        "observed": True,
        "status": "configured" if not mismatches else "drift",
        "note": "railway.toml deploy contract is present" if not mismatches else "railway.toml deploy contract drift",
        "mismatches": mismatches,
    }


def _observability_action(name: str, payload: dict) -> dict:
    template = _OBSERVABILITY_ACTIONS.get(name, {"owner": "Senior PM", "severity": "medium", "next_action": "Inspect the component probe and record a concrete recovery action.", "evidence_required": ["component-specific health evidence"]})
    return {
        "component": name,
        "status": payload.get("status") or ("red" if not payload.get("ok") else "not_observed"),
        "ok": bool(payload.get("ok")),
        "observed": _is_observed(payload),
        "owner": template["owner"],
        "severity": template["severity"],
        "next_action": template["next_action"],
        "evidence_required": template["evidence_required"],
        "detail": payload.get("note") or payload.get("error") or payload.get("last_seen") or payload.get("last_turn_at"),
    }


async def _observability_snapshot() -> dict:
    try:
        components = await gather_components()
    except Exception as exc:  # noqa: BLE001
        log.debug("observability snapshot failed: %s", exc)
        return {"source": "health_full", "ok": False, "fully_observed": False, "red_components": ["health_full"], "degraded_components": [], "actions": [_observability_action("health_full", {"ok": False, "status": "red", "error": str(exc)[:120]})]}

    components = {**components, "railway_deploy_config": _railway_deploy_config_component()}
    verdict = classify(components)
    ordered = verdict["red_components"] + verdict["degraded_components"]
    actions = [_observability_action(name, components[name]) for name in ordered]
    return {"source": "health_full", **verdict, "actions": actions}


def _nexus_one_status() -> dict:
    """Fail-closed synthetic status. Status route ≠ live registration."""
    from ..app_factory import app as fastapi_app

    return status_payload_for_app(fastapi_app)


@router.get("/live", dependencies=[Depends(require_auth)])
async def mission_control_live() -> dict:
    queue, pulse = await asyncio.gather(
        asyncio.to_thread(_cached_queue_snapshot),
        asyncio.to_thread(_cached_pulse_status),
    )
    return {
        "throughput": {"hourly": _hourly_throughput_24h()},
        "active_sessions": _active_sessions(),
        "recent_completions": _recent_completions(),
        "queue": queue,
        "pulse": pulse,
        "observability": await _observability_snapshot(),
        "claude_hud": _claude_session_hud(),
        "idea_pipeline": _idea_pipeline_snapshot(_repo_root()),
        "nexus_one": _nexus_one_status(),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
