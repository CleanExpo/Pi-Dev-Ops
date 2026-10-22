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
from ..idea_pipeline import daily_snapshot as _idea_pipeline_snapshot
from ..nexus_one.status import status_payload_for_app
from ..ticket_sweeper import status_snapshot as _ticket_sweeper_snapshot
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


def _queue_unavailable(reason: str) -> dict:
    """A queue we could not read. Nulls, never zeros: "0 urgent" is a measurement."""
    return {"available": False, "error": reason, "urgent": None, "high": None, "next_issue_id": None, "next_issue_title": None}


def _pulse_unavailable(reason: str) -> dict:
    """A pulse we could not read. `comments_today: 0` would claim a silent day."""
    return {"available": False, "error": reason, "last_at": None, "comments_today": None, "pulse_issue_id": None}


def _queue_snapshot() -> dict:
    """Displayed queue is the claimable autonomy queue (UNI-2648).

    Shape lives in queue_snapshot_from_issues — urgent/high/next_issue_*.
    The UNI-2647 contract walker follows this return; do not flatten it.
    """
    key = os.environ.get("LINEAR_API_KEY", "").strip()
    if not key:
        return _queue_unavailable("LINEAR_API_KEY is not set")
    registry = {p["project_id"] for p in autonomy._load_portfolio_projects()}
    issues = filter_claimable_issues(
        autonomy.fetch_todo_issues(key, fail_on_error=True),
        registered_project_ids=registry,
        priority_labels=autonomy._PRIORITY_FILTER,
    )
    return {"available": True, "error": None, **queue_snapshot_from_issues(issues)}


def _pulse_status() -> dict:
    # This read parents[2] — <repo>/app — while linear_pulse writes to
    # <repo>/.harness, so the heartbeat came from a path nothing ever wrote.
    state_file = _repo_root() / ".harness" / "linear-pulse-state.json"
    if not state_file.exists():
        return _pulse_unavailable("no pulse state recorded")
    try:
        state = json.loads(state_file.read_text())
    except Exception as exc:  # noqa: BLE001
        return _pulse_unavailable(f"pulse state unreadable: {type(exc).__name__}")
    pulse_id = state.get("pulse_issue_id") if isinstance(state, dict) else None
    if not pulse_id:
        return _pulse_unavailable("no pulse issue recorded")
    q = """
    query($id: String!) {
      issue(id: $id) {
        identifier
        comments(first: 50, orderBy: updatedAt) { nodes { createdAt } }
      }
    }
    """
    data = _linear_graphql(q, {"id": pulse_id})
    issue = (data or {}).get("issue")
    if not issue:
        return _pulse_unavailable("pulse issue not returned by Linear")
    nodes = (issue.get("comments") or {}).get("nodes") or []
    today = datetime.now(timezone.utc).date().isoformat()
    comments_today = sum(1 for n in nodes if (n.get("createdAt") or "").startswith(today))
    last_at = nodes[0].get("createdAt") if nodes else None
    return {"available": True, "error": None, "last_at": last_at, "comments_today": comments_today, "pulse_issue_id": issue.get("identifier") or pulse_id}


def _cached_queue_snapshot() -> dict:
    """Reuse the portfolio read across the 5-second live-view refreshes."""
    global _queue_cache
    if autonomy.linear_rate_limited():
        return _queue_unavailable("Linear rate limited")
    if not os.environ.get("LINEAR_API_KEY", "").strip():
        return _queue_snapshot()
    with _queue_cache_lock:
        if autonomy.linear_rate_limited():
            return _queue_unavailable("Linear rate limited")
        if _queue_cache is not None and time.monotonic() < _queue_cache[0]:
            return _queue_cache[1]
        try:
            snapshot = _queue_snapshot()
        except Exception as exc:  # noqa: BLE001 — reported as unavailable, never as 0
            log.warning("mission_control queue snapshot failed: %s", type(exc).__name__)
            return _queue_unavailable(f"Linear queue read failed: {type(exc).__name__}")
        if not autonomy.linear_rate_limited():
            _queue_cache = (time.monotonic() + _QUEUE_CACHE_SECONDS, snapshot)
        return snapshot


def _cached_pulse_status() -> dict:
    global _pulse_cache
    if autonomy.linear_rate_limited():
        return _pulse_unavailable("Linear rate limited")
    if not os.environ.get("LINEAR_API_KEY", "").strip():
        return _pulse_unavailable("LINEAR_API_KEY is not set")
    with _pulse_cache_lock:
        if autonomy.linear_rate_limited():
            return _pulse_unavailable("Linear rate limited")
        if _pulse_cache is not None and time.monotonic() < _pulse_cache[0]:
            return _pulse_cache[1]
        try:
            snapshot = _pulse_status()
        except Exception as exc:  # noqa: BLE001 — reported as unavailable, never as 0
            log.warning("mission_control pulse fetch failed: %s", type(exc).__name__)
            return _pulse_unavailable(f"Linear pulse read failed: {type(exc).__name__}")
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
        "evidence_required": ["railway.pi-dev-ops.toml contract check passes", "Railway latest deployment manifest matches Dockerfile + guarded bootstrap + /health"],
    },
    "hermes_gateway": {"owner": "Hermes/Codex operator", "severity": "high", "next_action": "On the Mac mini, restart the Hermes gateway (launchd ai.hermes.gateway) and confirm the mesh heartbeat (com.unite-group.mesh-heartbeat) is running, so a hermes-gateway agent row reports within five minutes.", "evidence_required": ["fresh mesh_agents hermes-gateway row in state working", "Mission Control fully_observed recalculation"]},
    "margot_route": {"owner": "Margot operator", "severity": "medium", "next_action": "Run a Margot turn or sync conversation evidence so .harness/margot/conversations has a fresh record.", "evidence_required": ["fresh Margot conversation JSONL", "last_turn_at within 24h"]},
    "openrouter": {"owner": "LLM routing steward", "severity": "medium", "next_action": "Generate a low-cost model-router heartbeat or restore the llm-cost log writer.", "evidence_required": ["fresh .harness/llm-cost.jsonl row"]},
    "supabase": {"owner": "Data/CRM operator", "severity": "high", "next_action": "Run supabase_health.health_check and repair whatever it reports so Mission Control proves Supabase reads are observable.", "evidence_required": ["supabase_health.health_check returns observed=true and ok=true", "integration health check evidence"]},
    "telegram_polling": {"owner": "Mobile/operator comms", "severity": "high", "next_action": "Start or repair Telegram polling heartbeat so .harness/telegram-poll-heartbeat updates within two minutes.", "evidence_required": ["fresh telegram-poll-heartbeat mtime", "operator alert route verified"]},
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _railway_deploy_config_component() -> dict:
    path = _repo_root() / "railway.pi-dev-ops.toml"
    if not path.exists():
        return {"ok": False, "observed": True, "status": "missing", "error": "railway.pi-dev-ops.toml is missing"}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return {"ok": False, "observed": True, "status": "invalid", "error": f"railway.pi-dev-ops.toml unreadable: {exc}"}

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
        "note": "railway.pi-dev-ops.toml deploy contract is present" if not mismatches else "railway.pi-dev-ops.toml deploy contract drift",
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
        "idea_pipeline": _idea_pipeline_snapshot(_repo_root()),
        "nexus_one": _nexus_one_status(),
        "ticket_sweeper": _ticket_sweeper_snapshot(),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
