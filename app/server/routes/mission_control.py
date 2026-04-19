"""
mission_control.py — /api/mission-control/live aggregator for the dashboard.

Single endpoint that powers the "live autonomy" view — polled every 5s by the
React LiveActivityFeed component. Returns everything the dashboard needs in one
shape so the frontend stays dumb + fast.

Shape:
  {
    "throughput": {"hourly": [int x 24]},      // completions per hour, UTC
    "active_sessions": [{id, repo, phase, elapsed_s, issue_id, last_log_tail}],
    "recent_completions": [{id, repo, branch, score, pr_url, completed_at}],
    "queue": {"urgent": int, "high": int, "next_issue_id": str | None},
    "pulse": {"last_at": iso | None, "comments_today": int, "pulse_issue_id": str | None},
    "ts": iso8601 now
  }

All Linear calls fail-soft to empty lists so the dashboard never breaks.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from ..auth import require_auth

log = logging.getLogger("pi-ceo.mission_control")
router = APIRouter(prefix="/api/mission-control", tags=["mission-control"])

_LINEAR_ENDPOINT = "https://api.linear.app/graphql"


# ── Helpers ─────────────────────────────────────────────────────────────────
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


# ── Throughput (hourly session completions) ─────────────────────────────────
def _hourly_throughput_24h() -> list[int]:
    """Return list of 24 ints — completions in each of the last 24 UTC hours.

    Reads from the /api/sessions in-memory state (cheap, no DB hit).
    """
    try:
        from .sessions import _sessions  # type: ignore

        now = datetime.now(timezone.utc)
        buckets = [0] * 24
        for sess in (_sessions or {}).values():
            status = getattr(sess, "status", None) or (
                sess.get("status") if isinstance(sess, dict) else None
            )
            if status not in ("complete", "shipped", "done"):
                continue
            completed = getattr(sess, "completed_at", None) or (
                sess.get("completed_at") if isinstance(sess, dict) else None
            )
            if not completed:
                continue
            try:
                dt = (
                    completed
                    if isinstance(completed, datetime)
                    else datetime.fromisoformat(str(completed).replace("Z", "+00:00"))
                )
            except (TypeError, ValueError):
                continue
            hours_ago = int((now - dt).total_seconds() // 3600)
            if 0 <= hours_ago < 24:
                buckets[23 - hours_ago] += 1
        return buckets
    except Exception as exc:  # noqa: BLE001
        log.debug("throughput read failed: %s", exc)
        return [0] * 24


# ── Active sessions ─────────────────────────────────────────────────────────
def _active_sessions() -> list[dict]:
    try:
        from .sessions import _sessions  # type: ignore

        out = []
        now = datetime.now(timezone.utc)
        for sid, sess in (_sessions or {}).items():
            status = getattr(sess, "status", None) or (
                sess.get("status") if isinstance(sess, dict) else None
            )
            if status not in ("created", "cloning", "building", "evaluating", "running"):
                continue
            started = getattr(sess, "started_at", None) or (
                sess.get("started_at") if isinstance(sess, dict) else None
            )
            elapsed = 0
            if started:
                try:
                    dt = (
                        started
                        if isinstance(started, datetime)
                        else datetime.fromisoformat(str(started).replace("Z", "+00:00"))
                    )
                    elapsed = int((now - dt).total_seconds())
                except (TypeError, ValueError):
                    pass
            out.append(
                {
                    "id": sid[:12],
                    "repo": (
                        getattr(sess, "repo_url", "") or ""
                    ).split("/")[-1]
                    or "?",
                    "phase": getattr(sess, "phase", None)
                    or (sess.get("phase") if isinstance(sess, dict) else status),
                    "status": status,
                    "elapsed_s": elapsed,
                    "issue_id": getattr(sess, "linear_issue_id", None)
                    or (sess.get("linear_issue_id") if isinstance(sess, dict) else None),
                    "last_log_tail": (getattr(sess, "last_log_line", "") or "")[:120],
                }
            )
        return out
    except Exception as exc:  # noqa: BLE001
        log.debug("active sessions read failed: %s", exc)
        return []


# ── Recent completions (last 6) ─────────────────────────────────────────────
def _recent_completions(limit: int = 6) -> list[dict]:
    try:
        from .sessions import _sessions  # type: ignore

        completed = []
        for sid, sess in (_sessions or {}).items():
            status = getattr(sess, "status", None) or (
                sess.get("status") if isinstance(sess, dict) else None
            )
            if status not in ("complete", "shipped", "done"):
                continue
            completed_at = getattr(sess, "completed_at", None) or (
                sess.get("completed_at") if isinstance(sess, dict) else None
            )
            completed.append(
                {
                    "id": sid[:12],
                    "repo": (getattr(sess, "repo_url", "") or "").split("/")[-1] or "?",
                    "branch": getattr(sess, "branch", None)
                    or (sess.get("branch") if isinstance(sess, dict) else None),
                    "score": getattr(sess, "evaluator_score", None)
                    or (
                        sess.get("evaluator_score")
                        if isinstance(sess, dict)
                        else None
                    ),
                    "pr_url": getattr(sess, "pr_url", None)
                    or (sess.get("pr_url") if isinstance(sess, dict) else None),
                    "issue_id": getattr(sess, "linear_issue_id", None)
                    or (sess.get("linear_issue_id") if isinstance(sess, dict) else None),
                    "completed_at": str(completed_at) if completed_at else None,
                }
            )
        completed.sort(key=lambda x: x.get("completed_at") or "", reverse=True)
        return completed[:limit]
    except Exception as exc:  # noqa: BLE001
        log.debug("recent completions read failed: %s", exc)
        return []


# ── Autonomy queue (Linear Urgent+High Todo) ───────────────────────────────
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
    return {
        "urgent": len(urgent),
        "high": len(high),
        "next_issue_id": next_issue.get("identifier"),
        "next_issue_title": (next_issue.get("title") or "")[:80],
    }


# ── Pulse status ────────────────────────────────────────────────────────────
def _pulse_status() -> dict:
    # Pulse issue id is persisted to .harness/linear-pulse-state.json
    try:
        from pathlib import Path

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
    return {
        "last_at": last_at,
        "comments_today": comments_today,
        "pulse_issue_id": issue.get("identifier") or pulse_id,
    }


# ── Route ────────────────────────────────────────────────────────────────────
@router.get("/live", dependencies=[Depends(require_auth)])
async def live_activity() -> dict:
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "throughput": {"hourly_24h": _hourly_throughput_24h()},
        "active_sessions": _active_sessions(),
        "recent_completions": _recent_completions(),
        "queue": _queue_snapshot(),
        "pulse": _pulse_status(),
    }
