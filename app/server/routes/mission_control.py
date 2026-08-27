"""
mission_control.py — /api/mission-control/live aggregator for the dashboard.

Single endpoint that powers the "live autonomy" view — polled every 5s by the
React LiveActivityFeed component. Returns everything the dashboard needs in one
shape so the frontend stays dumb + fast.
"""

from __future__ import annotations

import json
import logging
import os
import tomllib
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends

from ..auth import require_auth
from .health_full import gather_components, _is_observed

log = logging.getLogger("pi-ceo.mission_control")
router = APIRouter(prefix="/api/mission-control", tags=["mission-control"])

_LINEAR_ENDPOINT = "https://api.linear.app/graphql"


def _linear_graphql(query: str, variables: dict | None = None) -> dict:
    key = os.environ.get("LINEAR_API_KEY", "").strip()
    if not key:
        return {}
    payload = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        _LINEAR_ENDPOINT,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": key},
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            return (json.loads(resp.read()) or {}).get("data", {}) or {}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        log.debug("mission_control linear fetch failed: %s", exc)
        return {}


def _hourly_throughput_24h() -> list[int]:
    try:
        from .sessions import _sessions  # type: ignore

        now = datetime.now(timezone.utc)
        buckets = [0] * 24
        for sess in (_sessions or {}).values():
            status = getattr(sess, "status", None) or (sess.get("status") if isinstance(sess, dict) else None)
            if status not in ("complete", "shipped", "done"):
                continue
            completed = getattr(sess, "completed_at", None) or (sess.get("completed_at") if isinstance(sess, dict) else None)
            if not completed:
                continue
            try:
                dt = completed if isinstance(completed, datetime) else datetime.fromisoformat(str(completed).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                continue
            hours_ago = int((now - dt).total_seconds() // 3600)
            if 0 <= hours_ago < 24:
                buckets[23 - hours_ago] += 1
        return buckets
    except Exception as exc:  # noqa: BLE001
        log.debug("throughput read failed: %s", exc)
        return [0] * 24


def _active_sessions() -> list[dict]:
    try:
        from .sessions import _sessions  # type: ignore

        out = []
        now = datetime.now(timezone.utc)
        for sid, sess in (_sessions or {}).items():
            status = getattr(sess, "status", None) or (sess.get("status") if isinstance(sess, dict) else None)
            if status not in ("created", "cloning", "building", "evaluating", "running"):
                continue
            started = getattr(sess, "started_at", None) or (sess.get("started_at") if isinstance(sess, dict) else None)
            elapsed = 0
            if started:
                try:
                    dt = started if isinstance(started, datetime) else datetime.fromisoformat(str(started).replace("Z", "+00:00"))
                    elapsed = int((now - dt).total_seconds())
                except (TypeError, ValueError):
                    pass
            out.append({
                "id": sid[:12],
                "repo": (getattr(sess, "repo_url", "") or "").split("/")[-1] or "?",
                "phase": getattr(sess, "phase", None) or (sess.get("phase") if isinstance(sess, dict) else status),
                "status": status,
                "elapsed_s": elapsed,
                "issue_id": getattr(sess, "linear_issue_id", None) or (sess.get("linear_issue_id") if isinstance(sess, dict) else None),
                "last_log_tail": (getattr(sess, "last_log_line", "") or "")[:120],
            })
        return out
    except Exception as exc:  # noqa: BLE001
        log.debug("active sessions read failed: %s", exc)
        return []


def _recent_completions(limit: int = 6) -> list[dict]:
    try:
        from .sessions import _sessions  # type: ignore

        completed = []
        for sid, sess in (_sessions or {}).items():
            status = getattr(sess, "status", None) or (sess.get("status") if isinstance(sess, dict) else None)
            if status not in ("complete", "shipped", "done"):
                continue
            completed_at = getattr(sess, "completed_at", None) or (sess.get("completed_at") if isinstance(sess, dict) else None)
            completed.append({
                "id": sid[:12],
                "repo": (getattr(sess, "repo_url", "") or "").split("/")[-1] or "?",
                "branch": getattr(sess, "branch", None) or (sess.get("branch") if isinstance(sess, dict) else None),
                "score": getattr(sess, "evaluator_score", None) or (sess.get("evaluator_score") if isinstance(sess, dict) else None),
                "pr_url": getattr(sess, "pr_url", None) or (sess.get("pr_url") if isinstance(sess, dict) else None),
                "issue_id": getattr(sess, "linear_issue_id", None) or (sess.get("linear_issue_id") if isinstance(sess, dict) else None),
                "completed_at": str(completed_at) if completed_at else None,
            })
        completed.sort(key=lambda x: x.get("completed_at") or "", reverse=True)
        return completed[:limit]
    except Exception as exc:  # noqa: BLE001
        log.debug("recent completions read failed: %s", exc)
        return []


def _queue_snapshot() -> dict:
    q = """
    {
      urgent: issues(filter: {state: {type: {eq: "unstarted"}}, priority: {eq: 1}}, first: 20, orderBy: updatedAt) {
        nodes { identifier title }
      }
      high: issues(filter: {state: {type: {eq: "unstarted"}}, priority: {eq: 2}}, first: 20, orderBy: updatedAt) {
        nodes { identifier title }
      }
    }
    """
    data = _linear_graphql(q)
    urgent = (data.get("urgent") or {}).get("nodes") or []
    high = (data.get("high") or {}).get("nodes") or []
    next_issue = (urgent or high or [{}])[0]
    return {"urgent": len(urgent), "high": len(high), "next_issue_id": next_issue.get("identifier"), "next_issue_title": (next_issue.get("title") or "")[:80]}


def _pulse_status() -> dict:
    try:
        state_file = Path(__file__).resolve().parents[2] / ".harness" / "linear-pulse-state.json"
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


_OBSERVABILITY_ACTIONS = {
    "railway_deploy_config": {
        "owner": "Deploy/infra operator",
        "severity": "high",
        "next_action": "Restore Railway's repo-backed deploy contract: Dockerfile builder, guarded model-fabric bootstrap, and /health healthcheck.",
        "evidence_required": ["railway.toml contract check passes", "Railway latest deployment manifest matches Dockerfile + guarded bootstrap + /health"],
    },
    "hermes_gateway": {"owner": "Hermes/Codex operator", "severity": "high", "next_action": "Start or repair the Mac Mini Hermes heartbeat writer so .harness/hermes/heartbeat.jsonl updates within five minutes.", "evidence_required": ["fresh heartbeat.jsonl row", "Mission Control fully_observed recalculation"]},
    "margot_route": {"owner": "Margot operator", "severity": "medium", "next_action": "Run a Margot turn or sync conversation evidence so .harness/margot/conversations has a fresh record.", "evidence_required": ["fresh Margot conversation JSONL", "last_turn_at within 24h"]},
    "openrouter": {"owner": "LLM routing steward", "severity": "medium", "next_action": "Generate a low-cost model-router heartbeat or restore the llm-cost log writer.", "evidence_required": ["fresh .harness/llm-cost.jsonl row"]},
    "supabase": {"owner": "Data/CRM operator", "severity": "high", "next_action": "Implement or repair supabase_log.health_check so Mission Control proves Supabase writes are observable.", "evidence_required": ["supabase_log.health_check returns true", "integration health check evidence"]},
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
    red_components = sorted(name for name, payload in components.items() if not bool(payload.get("ok")))
    degraded_components = sorted(name for name, payload in components.items() if bool(payload.get("ok")) and not _is_observed(payload))
    actions = [_observability_action(name, components[name]) for name in red_components + degraded_components]
    return {"source": "health_full", "ok": not red_components, "fully_observed": not red_components and not degraded_components, "red_components": red_components, "degraded_components": degraded_components, "actions": actions}


@router.get("/live", dependencies=[Depends(require_auth)])
async def mission_control_live() -> dict:
    return {
        "throughput": {"hourly": _hourly_throughput_24h()},
        "active_sessions": _active_sessions(),
        "recent_completions": _recent_completions(),
        "queue": _queue_snapshot(),
        "pulse": _pulse_status(),
        "observability": await _observability_snapshot(),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
