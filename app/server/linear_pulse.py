"""
linear_pulse.py — Mandatory 15-minute Linear heartbeat across the whole system.

Why: the user wants Linear as the single-pane-of-glass for portfolio state. Every
15 min, this module posts:

  1. A status comment to every in-flight session's Linear ticket
     ("Phase: build (running), 12 min elapsed; last log: <tail>")

  2. A portfolio-heartbeat comment to the designated Linear "pulse" issue
     (auto-created if missing) with the current digest snapshot

  3. An alert comment on any session that's been in the same phase > 30 min
     (stuck-session detection — Linear is the source of truth, not the dashboard)

Called by app.server.cron_scheduler on a 15-min schedule ("*/15 * * * *").

Never raises to the caller. Every failure is logged. The pulse MUST keep firing
even if Linear is momentarily down — the next tick will catch up.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("pi-ceo.linear_pulse")

_LINEAR_ENDPOINT = "https://api.linear.app/graphql"
_STUCK_PHASE_MINUTES = 30
_PULSE_ISSUE_TITLE = "Pi-CEO Portfolio Pulse (auto)"
_STATE_FILE = Path(__file__).resolve().parent.parent.parent / ".harness" / "linear-pulse-state.json"


# ── Helpers ─────────────────────────────────────────────────────────────────
def _linear_key() -> str:
    return os.environ.get("LINEAR_API_KEY", "").strip()


def _graphql(query: str, variables: dict | None = None) -> dict:
    key = _linear_key()
    if not key:
        log.warning("linear_pulse: LINEAR_API_KEY not set — pulse skipped")
        return {}
    payload = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        _LINEAR_ENDPOINT,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": key},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return (json.loads(resp.read()) or {}).get("data", {}) or {}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        log.warning("linear_pulse: graphql error: %s", exc)
        return {}


def _load_state() -> dict:
    try:
        return json.loads(_STATE_FILE.read_text())
    except Exception:  # noqa: BLE001
        return {}


def _save_state(state: dict) -> None:
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _STATE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, indent=2))
        os.replace(tmp, _STATE_FILE)
    except Exception as exc:  # noqa: BLE001
        log.warning("linear_pulse: failed to persist state: %s", exc)


def _pulse_issue_id(state: dict) -> str | None:
    """Resolve the Portfolio Pulse issue id, creating if missing."""
    cached = state.get("pulse_issue_id")
    if cached:
        return cached

    team_id = os.environ.get("LINEAR_PULSE_TEAM_ID") or os.environ.get(
        "LINEAR_TEAM_ID"
    )
    project_id = os.environ.get("LINEAR_PULSE_PROJECT_ID") or os.environ.get(
        "LINEAR_PROJECT_ID"
    )
    if not team_id:
        return None

    # Search first to avoid duplicates
    search_q = """
    query($title: String!) {
      issues(filter: {title: {eq: $title}}, first: 1) {
        nodes { id identifier }
      }
    }
    """
    data = _graphql(search_q, {"title": _PULSE_ISSUE_TITLE})
    nodes = ((data or {}).get("issues") or {}).get("nodes") or []
    if nodes:
        state["pulse_issue_id"] = nodes[0].get("id")
        _save_state(state)
        return state["pulse_issue_id"]

    # Create the pulse issue
    mutation = """
    mutation($input: IssueCreateInput!) {
      issueCreate(input: $input) {
        success issue { id identifier url }
      }
    }
    """
    inp = {
        "teamId": team_id,
        "title": _PULSE_ISSUE_TITLE,
        "description": (
            "Auto-created by Pi-CEO linear_pulse. Receives a comment every "
            "15 min with the current portfolio snapshot.\n\n"
            "Do not close — system will recreate if missing."
        ),
        "priority": 0,
    }
    if project_id:
        inp["projectId"] = project_id
    data = _graphql(mutation, {"input": inp})
    issue = ((data or {}).get("issueCreate") or {}).get("issue")
    if not issue:
        log.warning("linear_pulse: failed to create pulse issue")
        return None
    state["pulse_issue_id"] = issue.get("id")
    _save_state(state)
    return state["pulse_issue_id"]


def _post_comment(issue_id: str, body: str) -> bool:
    if not issue_id or not body:
        return False
    mutation = """
    mutation($input: CommentCreateInput!) {
      commentCreate(input: $input) { success comment { id } }
    }
    """
    data = _graphql(mutation, {"input": {"issueId": issue_id, "body": body}})
    return bool(((data or {}).get("commentCreate") or {}).get("success"))


# ── Public entry points ─────────────────────────────────────────────────────
def _active_sessions() -> list[dict]:
    """In-flight session dicts via sessions.py's _sessions map."""
    try:
        from .routes.sessions import _sessions  # type: ignore

        out = []
        for sid, sess in list((_sessions or {}).items()):
            status = getattr(sess, "status", None) or (
                sess.get("status") if isinstance(sess, dict) else None
            )
            if not status or str(status).lower() in {
                "complete",
                "failed",
                "killed",
                "interrupted",
            }:
                continue
            out.append(
                {
                    "id": sid,
                    "issue_id": getattr(sess, "linear_issue_id", None)
                    or (sess.get("linear_issue_id") if isinstance(sess, dict) else None),
                    "phase": getattr(sess, "phase", None)
                    or (sess.get("phase") if isinstance(sess, dict) else "running"),
                    "started_at": getattr(sess, "started_at", None)
                    or (sess.get("started_at") if isinstance(sess, dict) else None),
                    "last_log": (
                        getattr(sess, "last_log_line", "") or ""
                    )[:200],
                }
            )
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("linear_pulse: could not read sessions: %s", exc)
        return []


def _elapsed_minutes(started_at: str | None) -> int:
    if not started_at:
        return 0
    try:
        dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return int((now - dt).total_seconds() // 60)
    except Exception:  # noqa: BLE001
        return 0


def run_pulse() -> dict:
    """Single pulse tick. Safe to call every 15 min.

    Returns summary counts — useful for the cron scheduler log.
    """
    now = datetime.now(timezone.utc).isoformat()
    state = _load_state()

    session_comments = 0
    stuck_alerts = 0

    # 1. Per-session comments
    for sess in _active_sessions():
        iid = sess.get("issue_id")
        if not iid:
            continue
        elapsed = _elapsed_minutes(sess.get("started_at"))
        body = (
            f"**Pulse** {now}\n"
            f"Phase: `{sess.get('phase', '?')}`\n"
            f"Elapsed: {elapsed} min\n"
            f"Session: `{sess.get('id', '?')[:8]}`\n"
            f"Last log: `{sess.get('last_log', '')[:150]}`"
        )
        if _post_comment(iid, body):
            session_comments += 1

        # Stuck detection: if same phase for >= STUCK threshold, flag
        key = f"stuck:{sess['id']}:{sess.get('phase', '?')}"
        last_seen = state.get(key, 0)
        if not last_seen:
            state[key] = int(datetime.now(timezone.utc).timestamp())
        else:
            minutes = (datetime.now(timezone.utc).timestamp() - last_seen) / 60
            if minutes >= _STUCK_PHASE_MINUTES and not state.get(f"{key}:alerted"):
                _post_comment(
                    iid,
                    f"🚨 **Stuck-phase alert** — session has been in "
                    f"`{sess.get('phase', '?')}` for {int(minutes)} min. "
                    "Consider killing + retrying.",
                )
                state[f"{key}:alerted"] = True
                stuck_alerts += 1

    # 2. Portfolio-pulse comment
    pulse_id = _pulse_issue_id(state)
    if pulse_id:
        try:
            from .digest import render_digest_text

            body = render_digest_text()
        except Exception as exc:  # noqa: BLE001
            body = f"digest unavailable: {exc}"
        _post_comment(pulse_id, body)

    _save_state(state)

    summary = {
        "ts": now,
        "session_comments": session_comments,
        "stuck_alerts": stuck_alerts,
        "pulse_posted": bool(pulse_id),
    }
    log.info("linear_pulse: %s", summary)
    return summary
