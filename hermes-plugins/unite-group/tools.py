"""Unite-Group plugin tools — Supabase + Linear data fetchers."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sb_request(url: str, key: str, path: str, params: str = "") -> Any:
    """Make a Supabase REST GET request and return parsed JSON."""
    full = f"{url}/rest/v1/{path}"
    if params:
        full += f"?{params}"
    req = urllib.request.Request(
        full,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _linear_request(query: str) -> Any:
    """Run a Linear GraphQL query."""
    api_key = os.environ.get("LINEAR_API_KEY", "")
    if not api_key:
        return None
    payload = json.dumps({"query": query}).encode()
    req = urllib.request.Request(
        "https://api.linear.app/graphql",
        data=payload,
        headers={
            "Authorization": api_key,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

UG_PORTFOLIO_HEALTH_SCHEMA = {
    "name": "ug_portfolio_health",
    "description": "Fetch latest portfolio health snapshot for all Unite-Group businesses from Supabase. Returns overall_health, security_score, and top issues per project.",
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Max rows to return (default 10)",
                "default": 10,
            }
        },
        "required": [],
    },
}

UG_CCW_KPIS_SCHEMA = {
    "name": "ug_ccw_kpis",
    "description": "Fetch CCW (first paying client) KPIs: ARR, open ticket count, NPS, and recent activity from Supabase.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

UG_WAVE_STATUS_SCHEMA = {
    "name": "ug_wave_status",
    "description": "Fetch current wave/milestone status from Linear — shows in-progress, completed, and blocked items across all Unite-Group projects.",
    "parameters": {
        "type": "object",
        "properties": {
            "project_filter": {
                "type": "string",
                "description": "Optional: filter to a specific project name (e.g. 'Synthex', 'Pi-CEO')",
            }
        },
        "required": [],
    },
}

UG_6PAGER_SCHEMA = {
    "name": "ug_6pager_summary",
    "description": "Fetch the most recent senior agent 6-pager digest from Supabase or the local wiki. Returns a structured summary of the latest strategic brief.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _handle_ug_portfolio_health(inputs: dict, **_kwargs) -> str:
    url = os.environ.get("SUPABASE_PI_CEO_URL") or os.environ.get("SUPABASE_UNITE_GROUP_URL", "")
    key = os.environ.get("SUPABASE_PI_CEO_SERVICE_KEY") or os.environ.get("SUPABASE_UNITE_GROUP_SERVICE_KEY", "")
    if not url or not key:
        return "Error: SUPABASE_PI_CEO_URL / SUPABASE_PI_CEO_SERVICE_KEY not set"
    limit = inputs.get("limit", 10)
    try:
        rows = _sb_request(
            url, key, "pi_ceo_health_snapshots",
            f"order=created_at.desc&limit={limit}&select=project_id,overall_health,security_score,top_issues,created_at"
        )
        if not rows:
            return "No health snapshots found in pi_ceo_health_snapshots."
        lines = ["**Portfolio Health Snapshot**\n"]
        for r in rows:
            h = r.get("overall_health", "?")
            s = r.get("security_score", "?")
            emoji = "🟢" if isinstance(h, int) and h >= 80 else ("🟡" if isinstance(h, int) and h >= 60 else "🔴")
            issues = r.get("top_issues", [])
            issue_str = ", ".join(issues[:2]) if issues else "—"
            ts = r.get("created_at", "")[:10]
            lines.append(f"{emoji} **{r.get('project_id', '?')}**: health={h}/100 sec={s} [{ts}]\n  Issues: {issue_str}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching portfolio health: {e}"


def _handle_ug_ccw_kpis(inputs: dict, **_kwargs) -> str:
    url = os.environ.get("SUPABASE_UNITE_GROUP_URL", "")
    key = os.environ.get("SUPABASE_UNITE_GROUP_SERVICE_KEY", "")
    if not url or not key:
        return "Error: SUPABASE_UNITE_GROUP_URL / SUPABASE_UNITE_GROUP_SERVICE_KEY not set"
    try:
        results = []
        # Try clients table
        try:
            clients = _sb_request(url, key, "clients", "select=id,name,arr,status&order=arr.desc.nullslast&limit=5")
            if clients:
                results.append("**CCW Clients:**")
                for c in clients:
                    results.append(f"  • {c.get('name', '?')}: ARR=${c.get('arr', '?'):,} status={c.get('status', '?')}")
        except Exception:
            pass
        # Try tickets/jobs table
        try:
            tickets = _sb_request(url, key, "jobs", "select=id,status&limit=200")
            if tickets:
                open_count = sum(1 for t in tickets if t.get("status") not in ("completed", "closed", "cancelled"))
                results.append(f"**Open Jobs/Tickets:** {open_count}")
        except Exception:
            pass
        # Try wiki_pages for CCW data
        try:
            pages = _sb_request(url, key, "wiki_pages", "select=title,updated_at&title=like.*CCW*&limit=3")
            if pages:
                results.append("**CCW Wiki Pages:**")
                for p in pages:
                    results.append(f"  • {p.get('title', '?')} (updated {p.get('updated_at', '')[:10]})")
        except Exception:
            pass
        if not results:
            return "No CCW KPI data found. Tables may need schema alignment."
        return "\n".join(results)
    except Exception as e:
        return f"Error fetching CCW KPIs: {e}"


def _handle_ug_wave_status(inputs: dict, **_kwargs) -> str:
    project_filter = inputs.get("project_filter", "")
    query = """
    query {
      projects(first: 20) {
        nodes {
          name
          state
          progress
          targetDate
          updatedAt
          milestones(first: 5) {
            nodes { name targetDate sortOrder }
          }
        }
      }
    }
    """
    try:
        data = _linear_request(query)
        if not data:
            return "Error: LINEAR_API_KEY not set or Linear query failed"
        projects = data.get("data", {}).get("projects", {}).get("nodes", [])
        if project_filter:
            projects = [p for p in projects if project_filter.lower() in p.get("name", "").lower()]
        if not projects:
            return f"No Linear projects found{' matching ' + project_filter if project_filter else ''}."
        lines = ["**Wave / Project Status (Linear)**\n"]
        for p in projects:
            name = p.get("name", "?")
            state = p.get("state", "?")
            progress = p.get("progress", 0)
            target = (p.get("targetDate") or "")[:10] or "—"
            lines.append(f"**{name}** — {state} ({int(progress * 100)}%) target={target}")
            milestones = p.get("milestones", {}).get("nodes", [])
            for m in milestones[:3]:
                lines.append(f"  · {m.get('name', '?')} (due {(m.get('targetDate') or '')[:10] or '—'})")
        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching wave status: {e}"


def _handle_ug_6pager_summary(inputs: dict, **_kwargs) -> str:
    url = os.environ.get("SUPABASE_UNITE_GROUP_URL", "")
    key = os.environ.get("SUPABASE_UNITE_GROUP_SERVICE_KEY", "")
    # Try Supabase first
    if url and key:
        try:
            rows = _sb_request(
                url, key, "wiki_pages",
                "title=like.*6-pager*,or=(title.like.*6pager*,title.like.*senior-agent*)&order=updated_at.desc&limit=3&select=title,content,updated_at"
            )
            if rows:
                r = rows[0]
                content = r.get("content", "")[:1500]
                return f"**6-Pager: {r.get('title', '?')}** (updated {r.get('updated_at', '')[:10]})\n\n{content}"
        except Exception:
            pass
    # Fall back to local wiki
    import glob
    import os
    wiki_dir = os.path.expanduser("~/2nd Brain/2nd Brain/Wiki")
    patterns = ["*6-pager*", "*6pager*", "*senior-agent-brief*"]
    for pat in patterns:
        files = sorted(glob.glob(os.path.join(wiki_dir, pat)), key=os.path.getmtime, reverse=True)
        if files:
            with open(files[0]) as f:
                content = f.read()[:1500]
            return f"**6-Pager (local):** {os.path.basename(files[0])}\n\n{content}"
    return "No 6-pager documents found in Supabase or local wiki."
