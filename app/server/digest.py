"""
digest.py — Portfolio digest assembler.

Single function: `render_digest_text()` returns a mobile-friendly markdown
snapshot of the whole Pi-CEO state.

Sources:
  - Linear GraphQL  (open tickets per project, transitions in last 24 h)
  - Pipeline summaries  (app.server.pipeline.list_pipelines)
  - Autonomy poller  (app.server.autonomy — last-tick timestamp, sessions spawned)
  - Cron runs  (app.server.cron_store — last 10 runs, failures highlighted)

Designed to fit in a single Telegram message (<4096 chars).
Used by:
  - /api/telegram/digest  (on-demand)
  - app.server.cron_scheduler  at 08:00 + 20:00 local time (mandatory push)
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("pi-ceo.digest")

_LINEAR_ENDPOINT = "https://api.linear.app/graphql"
_DIGEST_MAX_CHARS = 3800  # leave headroom under Telegram 4096 cap


# ── Linear helpers ──────────────────────────────────────────────────────────
def _linear_key() -> str:
    return os.environ.get("LINEAR_API_KEY", "").strip()


def _linear_graphql(query: str, variables: dict | None = None) -> dict:
    key = _linear_key()
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
        with urllib.request.urlopen(req, timeout=15) as resp:
            return (json.loads(resp.read()) or {}).get("data", {}) or {}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        log.warning("digest: linear fetch failed: %s", exc)
        return {}


def _projects_json() -> list[dict]:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / ".harness" / "projects.json"
        if candidate.is_file():
            try:
                return json.loads(candidate.read_text()).get("projects", []) or []
            except Exception:  # noqa: BLE001
                return []
    return []


def _linear_activity_24h() -> dict:
    """Return {project_id: {open: N, inflight: N, done24h: N}} snapshot."""
    projects = _projects_json()
    if not projects:
        return {}

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    # One GraphQL call per project keeps things simple and within Linear limits
    out: dict[str, dict] = {}
    for p in projects:
        proj_id = p.get("id", "?")
        linear_proj = p.get("linear_project_id")
        if not linear_proj:
            continue
        q = """
        query($projId: String!, $since: DateTimeOrDuration!) {
          project(id: $projId) {
            issues { nodes { state { type } } }
            done: issues(filter: {completedAt: {gte: $since}}) {
              nodes { identifier title }
            }
          }
        }
        """
        data = _linear_graphql(q, {"projId": linear_proj, "since": cutoff})
        proj = (data or {}).get("project") or {}
        nodes = (proj.get("issues") or {}).get("nodes") or []
        open_n = sum(
            1
            for n in nodes
            if (n.get("state") or {}).get("type") in {"backlog", "unstarted", "triage"}
        )
        inflight = sum(
            1 for n in nodes if (n.get("state") or {}).get("type") == "started"
        )
        done24 = len(((proj.get("done") or {}).get("nodes") or []))
        out[proj_id] = {"open": open_n, "inflight": inflight, "done24h": done24}
    return out


def _autonomy_snapshot() -> dict:
    try:
        from . import autonomy

        return {
            "last_tick": getattr(autonomy, "_LAST_TICK_AT", None),
            "sessions_spawned": getattr(autonomy, "_SESSIONS_SPAWNED", 0),
            "enabled": os.environ.get("TAO_AUTONOMY_ENABLED", "1") != "0",
        }
    except Exception:  # noqa: BLE001
        return {"last_tick": None, "sessions_spawned": 0, "enabled": False}


def _pipelines_inflight() -> list[dict]:
    try:
        from .pipeline import list_pipelines

        summaries = list_pipelines() or []
    except Exception:  # noqa: BLE001
        return []
    inflight = []
    for s in summaries:
        status = (s.get("status") or "").lower()
        if status in {"running", "in_progress", "pending"}:
            inflight.append(
                {
                    "id": s.get("pipeline_id", "?")[:8],
                    "issue": s.get("linear_issue_id") or "-",
                    "phase": s.get("current_phase") or status,
                }
            )
    return inflight[:10]


# ── Renderer ────────────────────────────────────────────────────────────────
def render_digest_text() -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"📰 <b>Pi-CEO Portfolio Digest</b> — {now}", ""]

    # Autonomy
    a = _autonomy_snapshot()
    autonomy_line = (
        f"🤖 Autonomy: {'ON' if a['enabled'] else 'OFF'}, "
        f"sessions spawned (run): {a['sessions_spawned']}"
    )
    if a["last_tick"]:
        autonomy_line += f" · last tick {a['last_tick']}"
    lines.append(autonomy_line)

    # Per-project Linear activity
    activity = _linear_activity_24h()
    if activity:
        lines.append("")
        lines.append("📂 <b>By project (last 24 h)</b>")
        for pid, counts in sorted(activity.items()):
            lines.append(
                f"  • {pid}: open {counts['open']}, in-flight "
                f"{counts['inflight']}, done {counts['done24h']}"
            )
    else:
        lines.append("")
        lines.append("📂 Linear snapshot unavailable (check LINEAR_API_KEY).")

    # In-flight pipelines
    inflight = _pipelines_inflight()
    if inflight:
        lines.append("")
        lines.append(f"🛠 <b>In-flight pipelines</b> ({len(inflight)})")
        for ip in inflight:
            lines.append(f"  • {ip['id']} ({ip['issue']}) → {ip['phase']}")

    rendered = "\n".join(lines)
    if len(rendered) > _DIGEST_MAX_CHARS:
        rendered = rendered[: _DIGEST_MAX_CHARS - 20] + "\n…(truncated)"
    return rendered


# ── Telegram push ───────────────────────────────────────────────────────────
def push_digest_to_telegram(chat_id: str | None = None) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    target = (
        chat_id
        or os.environ.get("TELEGRAM_ALERT_CHAT_ID", "")
        or os.environ.get("TELEGRAM_DIGEST_CHAT_ID", "")
    ).strip()
    if not token or not target:
        log.warning("digest: TELEGRAM_BOT_TOKEN or chat id missing — skipping push")
        return False
    try:
        body = json.dumps(
            {
                "chat_id": target,
                "text": render_digest_text(),
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
        ).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError) as exc:
        log.error("digest: telegram push failed: %s", exc)
        return False
