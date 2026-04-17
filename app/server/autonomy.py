"""
autonomy.py — Linear Todo poller + autonomous build pickup (RA-584).

Polls the Pi-Dev-Ops Linear project every TAO_AUTONOMY_POLL_INTERVAL seconds
(default 300) for Urgent/High priority Todo issues. For each one:
  1. Transition → In Progress
  2. Build a structured brief
  3. Trigger create_session() to start the 5-phase build pipeline
  4. On failure, revert → Todo + comment + retry counter

All actions logged to .harness/autonomy.jsonl.

Kill switch: TAO_AUTONOMY_ENABLED=0  (default: on)
"""
import asyncio
import json
import logging
import os
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

log = logging.getLogger("pi-ceo.autonomy")

_LINEAR_ENDPOINT = "https://api.linear.app/graphql"
_AUTONOMY_LOG = (
    Path(os.path.dirname(__file__)).parents[1] / ".harness" / "autonomy.jsonl"
)

# Pi - Dev -Ops project / team constants (matches .harness/projects.json)
_PROJECT_ID = "f45212be-3259-4bfb-89b1-54c122c939a7"
_TEAM_ID    = "a8a52f07-63cf-4ece-9ad2-3e3bd3c15673"
_DEFAULT_REPO_URL = "https://github.com/CleanExpo/Pi-Dev-Ops"

# RA-1289 — portfolio registry. Poller spans every project in .harness/projects.json
# so Urgent/High Todos on target-repo boards (Synthex, Unite-Group, CARSI, DR-NRPG…)
# trigger autonomous builds — not just Pi-Dev-Ops's own board.
_PROJECTS_JSON = (
    Path(os.path.dirname(__file__)).parents[1] / ".harness" / "projects.json"
)


def _load_portfolio_projects() -> list[dict]:
    """Load `.harness/projects.json` → list of dicts with the fields the poller needs.

    Each entry: {project_id, team_id, repo_url, name}.
    Projects without `linear_project_id` are skipped (can't filter by project).
    The Pi-Dev-Ops entry is always included as the first item for backwards compat.
    """
    try:
        registry = json.loads(_PROJECTS_JSON.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Autonomy: projects.json load failed (%s) — falling back to Pi-Dev-Ops only", exc)
        return [{
            "project_id": _PROJECT_ID,
            "team_id": _TEAM_ID,
            "repo_url": _DEFAULT_REPO_URL,
            "name": "Pi - Dev -Ops",
        }]

    out: list[dict] = []
    for p in registry.get("projects", []):
        project_id = p.get("linear_project_id")
        team_id    = p.get("linear_team_id")
        repo       = p.get("repo")
        if not project_id or not team_id or not repo:
            continue
        out.append({
            "project_id": project_id,
            "team_id":    team_id,
            "repo_url":   f"https://github.com/{repo}",
            "name":       p.get("linear_project_name") or p.get("id") or repo,
        })
    return out

# In-memory state (for /api/autonomy/status)
_last_poll_at: float = 0.0
_poll_count: int = 0
_recent_events: list[dict] = []


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _gql(api_key: str, query: str, variables: dict | None = None) -> dict[str, Any]:
    payload = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        _LINEAR_ENDPOINT,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": api_key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Linear HTTP {exc.code}: {body}") from exc
    if "errors" in data:
        raise RuntimeError(f"Linear GQL errors: {data['errors']}")
    return data.get("data", {})


def _log_event(event: dict) -> None:
    global _recent_events
    entry = {**event, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    _AUTONOMY_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(_AUTONOMY_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    _recent_events.append(entry)
    _recent_events = _recent_events[-20:]  # keep last 20 in memory


# ---------------------------------------------------------------------------
# Linear API calls
# ---------------------------------------------------------------------------

_TODO_ISSUES_QUERY = """
query TodoIssues($projectId: String!) {
    project(id: $projectId) {
        issues(filter: {
            state: { type: { in: ["unstarted"] } }
            priority: { lte: 2 }
        }, first: 10, orderBy: updatedAt) {
            nodes {
                id
                identifier
                title
                description
                priority
                url
                state { id name type }
                labels { nodes { name } }
            }
        }
    }
}
"""


def fetch_todo_issues(api_key: str) -> list[dict]:
    """Fetch Urgent + High priority Todo issues across every portfolio project.

    RA-1289 — iterates `.harness/projects.json` so the poller picks up tickets
    filed in target-repo boards (Synthex, Unite-Group, CARSI, DR-NRPG, …), not
    just Pi-Dev-Ops. Each returned issue is annotated with `_repo_url`,
    `_team_id`, and `_project_name` so downstream transitions / comments /
    session creation route to the correct board.

    Per-project fetch failures are logged but don't abort the full poll cycle.
    Issues are deduped by id (should never collide, but belt-and-braces).
    """
    projects = _load_portfolio_projects()
    seen: set[str] = set()
    merged: list[dict] = []

    for p in projects:
        try:
            data = _gql(api_key, _TODO_ISSUES_QUERY, {"projectId": p["project_id"]})
        except Exception as exc:
            log.warning("Autonomy: project %s fetch failed: %s", p["name"], exc)
            continue

        nodes = (data.get("project") or {}).get("issues", {}).get("nodes") or []
        for issue in nodes:
            iid = issue.get("id")
            if not iid or iid in seen:
                continue
            seen.add(iid)
            # Annotate with mapped project context so the poller can route
            # transitions/comments to the correct team and start the session
            # against the right repo without a `repo:` label.
            issue["_repo_url"]     = p["repo_url"]
            issue["_team_id"]      = p["team_id"]
            issue["_project_name"] = p["name"]
            merged.append(issue)

    # Sort: priority asc (1=Urgent first), then updatedAt (already queried ordered)
    merged.sort(key=lambda i: i.get("priority", 3))
    return merged


def _resolve_state_id(api_key: str, state_name: str, team_id: str = _TEAM_ID) -> str:
    """Resolve a human-readable state name to a Linear state ID for a given team.

    RA-1289 — accepts `team_id` so transitions work on any portfolio team, not
    just Pi-Dev-Ops. Defaults to `_TEAM_ID` for backwards compat with any caller
    still operating on the Pi-Dev-Ops board.
    """
    query = """
    query TeamStates($teamId: String!) {
        team(id: $teamId) {
            states { nodes { id name } }
        }
    }
    """
    data = _gql(api_key, query, {"teamId": team_id})
    states = (data.get("team") or {}).get("states", {}).get("nodes", [])
    target = next((s for s in states if s["name"].lower() == state_name.lower()), None)
    if not target:
        raise RuntimeError(f"State '{state_name}' not found in team {team_id} workflow")
    return target["id"]


def transition_issue(api_key: str, issue_id: str, state_name: str, team_id: str = _TEAM_ID) -> None:
    """Move a Linear issue to the named state (e.g. 'In Progress', 'Todo').

    RA-1289 — `team_id` defaults to Pi-Dev-Ops for compat; poller passes the
    issue's mapped team so cross-project tickets transition correctly.
    """
    state_id = _resolve_state_id(api_key, state_name, team_id=team_id)
    mutation = """
    mutation UpdateIssue($id: String!, $stateId: String!) {
        issueUpdate(id: $id, input: { stateId: $stateId }) { success }
    }
    """
    _gql(api_key, mutation, {"id": issue_id, "stateId": state_id})


def comment_on_issue(api_key: str, issue_id: str, body: str) -> None:
    """Post a comment on a Linear issue."""
    mutation = """
    mutation CreateComment($issueId: String!, $body: String!) {
        commentCreate(input: { issueId: $issueId, body: $body }) { success }
    }
    """
    _gql(api_key, mutation, {"issueId": issue_id, "body": body})


# ---------------------------------------------------------------------------
# Brief construction
# ---------------------------------------------------------------------------

def _extract_repo_url(issue: dict) -> str:
    """Resolve repo URL for an issue.

    Priority (highest first):
      1. `repo:` label (explicit override on the ticket)
      2. `repo:` line in the description (legacy override)
      3. RA-1289 — mapped `_repo_url` annotation from `fetch_todo_issues`
         (picked up from `.harness/projects.json` for the issue's project)
      4. Pi-Dev-Ops default

    Overrides 1+2 still win because some cross-project tickets target a
    different repo than their Linear project's default (e.g. a ticket in the
    Pi-Dev-Ops project that asks for a fix in a sibling repo).
    """
    labels = [ln["name"] for ln in (issue.get("labels") or {}).get("nodes", [])]
    for label in labels:
        if label.startswith("repo:"):
            return label.replace("repo:", "").strip()
    desc = issue.get("description", "") or ""
    for line in desc.splitlines():
        if line.startswith("repo:"):
            return line.replace("repo:", "").strip()
    mapped = issue.get("_repo_url")
    if mapped:
        return mapped
    return _DEFAULT_REPO_URL


def _build_brief(issue: dict) -> str:
    """Build a structured brief from a Linear issue dict."""
    priority_map = {1: "URGENT", 2: "HIGH", 3: "NORMAL", 4: "LOW"}
    priority_label = priority_map.get(issue.get("priority", 3), "NORMAL")
    title = issue.get("title", "Untitled")
    desc = (issue.get("description") or "").strip()
    brief = f"[{priority_label}] {title}\n\n"
    if desc:
        brief += f"Description:\n{desc}\n\n"
    brief += (
        f"Linear ticket: {issue.get('identifier')} — {issue.get('url')}\n"
        "Triggered automatically by Pi-CEO autonomous poller.\n"
    )
    return brief


# ---------------------------------------------------------------------------
# Poller
# ---------------------------------------------------------------------------

async def linear_todo_poller() -> None:
    """
    Background coroutine. Every TAO_AUTONOMY_POLL_INTERVAL seconds:
      - fetch Urgent/High Todo issues from Linear
      - for each one with a repo URL, fire a build session
    """
    from . import config  # late import to avoid circular
    from .sessions import create_session

    global _last_poll_at, _poll_count

    interval = int(os.environ.get("TAO_AUTONOMY_POLL_INTERVAL", "300"))
    # Startup delay — small grace period so the API is fully up before poll #1,
    # but NOT a full interval. Previously this was `await asyncio.sleep(interval)`
    # which meant after every Railway restart the poller sat idle for 5 full
    # minutes before its first fetch. That bootstrap delay is what made the
    # system look "stuck" and required a manual prompt to kick it back into life.
    startup_delay = int(os.environ.get("TAO_AUTONOMY_STARTUP_DELAY", "10"))
    log.info(
        "Autonomy poller started (interval=%ds, startup_delay=%ds, enabled=%s)",
        interval, startup_delay, config.AUTONOMY_ENABLED,
    )

    # Do-while: first iteration fires after `startup_delay` seconds, subsequent
    # iterations wait the full `interval`.
    first_iter = True
    while True:
        await asyncio.sleep(startup_delay if first_iter else interval)
        first_iter = False

        if not config.AUTONOMY_ENABLED:
            log.debug("Autonomy poller: disabled (TAO_AUTONOMY_ENABLED=0)")
            continue

        if not config.LINEAR_API_KEY:
            # Warn loudly EVERY poll, not just once — this was the silent-failure
            # mode that made Pi-Dev-Ops look healthy while nothing was happening.
            log.warning(
                "Autonomy poller: LINEAR_API_KEY not set — skipping poll #%d (check Railway env vars)",
                _poll_count + 1,
            )
            continue

        _last_poll_at = time.time()
        _poll_count += 1
        log.info("Autonomy poll #%d", _poll_count)

        try:
            issues = fetch_todo_issues(config.LINEAR_API_KEY)
        except Exception as exc:
            log.error("Autonomy poll #%d: fetch failed: %s", _poll_count, exc)
            _log_event({"action": "poll_error", "poll": _poll_count, "error": str(exc)})
            continue

        log.info("Autonomy poll #%d: %d todo issues found", _poll_count, len(issues))
        _log_event({"action": "poll", "poll": _poll_count, "found": len(issues)})

        for issue in issues:
            issue_id   = issue["id"]
            identifier = issue.get("identifier", "?")
            title      = issue.get("title", "?")
            repo_url   = _extract_repo_url(issue)
            team_id    = issue.get("_team_id", _TEAM_ID)  # RA-1289 — mapped team

            log.info(
                "Autonomy: processing %s '%s' repo=%s team=%s",
                identifier, title, repo_url, team_id,
            )

            # --- Transition to In Progress ---
            try:
                transition_issue(config.LINEAR_API_KEY, issue_id, "In Progress", team_id=team_id)
            except Exception as exc:
                log.error("Autonomy: transition failed for %s: %s", identifier, exc)
                _log_event({
                    "action": "transition_error",
                    "ticket": identifier,
                    "title": title,
                    "error": str(exc),
                })
                continue

            _log_event({
                "action": "transition_to_in_progress",
                "ticket": identifier,
                "title": title,
                "repo_url": repo_url,
            })

            # --- Fire build session ---
            brief = _build_brief(issue)
            try:
                session = await create_session(
                    repo_url=repo_url,
                    brief=brief,
                    model="sonnet",
                    linear_issue_id=issue_id,
                    autonomy_triggered=True,
                )
                log.info("Autonomy: session %s started for %s", session.id, identifier)
                _log_event({
                    "action": "session_started",
                    "ticket": identifier,
                    "title": title,
                    "session_id": session.id,
                    "repo_url": repo_url,
                })
                try:
                    comment_on_issue(
                        config.LINEAR_API_KEY,
                        issue_id,
                        (
                            f"🤖 **Pi-CEO autonomous session started**\n\n"
                            f"- Session ID: `{session.id}`\n"
                            f"- Repo: {repo_url}\n"
                            f"- Triggered by: autonomy poller (poll #{_poll_count})"
                        ),
                    )
                except Exception as exc:
                    log.warning("Autonomy: comment post failed for %s: %s", identifier, exc)

            except RuntimeError as exc:
                # Max sessions or recoverable error — revert to Todo
                log.warning("Autonomy: session start failed for %s: %s", identifier, exc)
                _log_event({
                    "action": "session_error",
                    "ticket": identifier,
                    "title": title,
                    "error": str(exc),
                })
                try:
                    transition_issue(config.LINEAR_API_KEY, issue_id, "Todo", team_id=team_id)
                    comment_on_issue(
                        config.LINEAR_API_KEY,
                        issue_id,
                        f"⚠️ Pi-CEO session start failed — reverted to Todo.\nError: `{exc}`",
                    )
                except Exception:
                    pass

            except Exception as exc:
                log.error("Autonomy: unexpected error for %s: %s", identifier, exc)
                _log_event({
                    "action": "session_error",
                    "ticket": identifier,
                    "title": title,
                    "error": str(exc),
                })


# ---------------------------------------------------------------------------
# Status (for /api/autonomy/status endpoint)
# ---------------------------------------------------------------------------

def _calc_effective_autonomy(events: list[dict]) -> dict:
    """
    RA-626 — Compute Effective Autonomy runtime metric from in-memory events.

    Metric definition:
      effective_autonomy_pct = poll_success_rate × session_success_rate × 100

    Where:
      poll_success_rate  = successful_polls / (successful_polls + poll_errors)
      session_success_rate = sessions_started / (sessions_started + session_errors)

    A value of 100 means every poll succeeded AND every session it attempted
    launched without error. Partial credit is given for partially healthy runs.
    Returns None for each sub-rate when there is no data yet.
    """
    polls           = sum(1 for e in events if e.get("action") == "poll")
    poll_errors     = sum(1 for e in events if e.get("action") == "poll_error")
    started         = sum(1 for e in events if e.get("action") == "session_started")
    errors          = sum(1 for e in events if e.get("action") == "session_error")
    _transitions_ok = sum(1 for e in events if e.get("action") == "transition_to_in_progress")  # noqa: F841
    transition_errs = sum(1 for e in events if e.get("action") == "transition_error")
    issues_found    = sum(e.get("found", 0) for e in events if e.get("action") == "poll")

    total_polls    = polls + poll_errors
    total_sessions = started + errors

    poll_rate    = polls / total_polls       if total_polls    > 0 else None
    session_rate = started / total_sessions  if total_sessions > 0 else None
    pickup_rate  = started / issues_found    if issues_found   > 0 else None

    # Composite: treat None sub-rates as 1.0 (no data = assume healthy)
    effective_pct = round(
        (poll_rate if poll_rate is not None else 1.0) *
        (session_rate if session_rate is not None else 1.0) * 100,
        1,
    )

    return {
        "effective_autonomy_pct": effective_pct,
        "poll_success_rate_pct": round(poll_rate * 100, 1) if poll_rate is not None else None,
        "session_success_rate_pct": round(session_rate * 100, 1) if session_rate is not None else None,
        "pickup_rate_pct": round(pickup_rate * 100, 1) if pickup_rate is not None else None,
        "sessions_started": started,
        "session_errors": errors,
        "transition_errors": transition_errs,
        "issues_found_window": issues_found,
        "window_size": len(events),
    }


def autonomy_status() -> dict:
    """Return poller heartbeat + recent events for the status endpoint."""
    from . import config
    now = time.time()
    age = round(now - _last_poll_at) if _last_poll_at else None
    return {
        "enabled": config.AUTONOMY_ENABLED,
        "poll_interval_s": int(os.environ.get("TAO_AUTONOMY_POLL_INTERVAL", "300")),
        "last_poll_at": _last_poll_at or None,
        "last_poll_ago_s": age,
        "stale": age is not None and age > 900,
        "poll_count": _poll_count,
        "effective_autonomy": _calc_effective_autonomy(_recent_events),  # RA-626
        "recent_events": _recent_events,
    }
