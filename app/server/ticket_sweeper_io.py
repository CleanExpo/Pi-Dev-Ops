"""ticket_sweeper_io.py — Linear queries and GitHub PR facts for the nightly
ticket sweeper (``ticket_sweeper.py``). Read-only: every write goes through the
autonomy helpers from the sweeper itself, behind its dry-run flag.

Kept separate so the decision module stays under the 300-line ceiling and the
tests can replace ``autonomy._gql`` / ``github_get`` without a network.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import datetime, timedelta, timezone

from . import autonomy

_GITHUB_API = "https://api.github.com"
_PR_URL_RE = re.compile(r"https://github\.com/([\w.-]+/[\w.-]+)/pull/(\d+)")

_ISSUE_FIELDS = """
    id identifier title updatedAt description
    state { id name type }
    labels { nodes { name } }
    attachments { nodes { url } }
    inverseRelations(first: 20) { nodes { type issue { identifier state { type } } } }
"""

_STARTED_QUERY = """
query SweeperStarted($projectId: String!, $before: DateTimeOrDuration!) {
    project(id: $projectId) {
        issues(filter: {
            state: { type: { eq: "started" } }
            updatedAt: { lt: $before }
        }, first: 50) { nodes { %s } }
    }
}
""" % _ISSUE_FIELDS

_IN_REVIEW_QUERY = """
query SweeperInReview($projectId: String!) {
    project(id: $projectId) {
        issues(filter: { state: { name: { eq: "In Review" } } }, first: 50) {
            nodes { %s }
        }
    }
}
""" % _ISSUE_FIELDS

# A failed build lands in Todo (session_linear: failed → Todo). Look back a week
# so a skipped night never loses one; acting moves the ticket out of Todo.
_RECENT_TODO_QUERY = """
query SweeperRecentTodo($projectId: String!, $after: DateTimeOrDuration!) {
    project(id: $projectId) {
        issues(filter: {
            state: { type: { eq: "unstarted" } }
            updatedAt: { gt: $after }
        }, first: 50) { nodes { %s comments(first: 20) { nodes { body } } } }
    }
}
""" % _ISSUE_FIELDS


def _iso_days_ago(days: int, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return (now - timedelta(days=days)).isoformat()


def fetch_buckets(api_key: str, *, stale_days: int, now: datetime | None = None) -> tuple[dict, list[str]]:
    """Fetch the three candidate buckets across every portfolio project.

    Returns ``({"stale": [...], "in_review": [...], "recent_todo": [...]}, errors)``.
    A project that fails to fetch is recorded in ``errors`` — never read as
    "that project has no tickets".
    """
    buckets: dict[str, list[dict]] = {"stale": [], "in_review": [], "recent_todo": []}
    errors: list[str] = []
    seen: dict[str, set[str]] = {k: set() for k in buckets}
    plan = (
        ("stale", _STARTED_QUERY, {"before": _iso_days_ago(stale_days, now)}),
        ("in_review", _IN_REVIEW_QUERY, {}),
        ("recent_todo", _RECENT_TODO_QUERY, {"after": _iso_days_ago(7, now)}),
    )
    for p in autonomy._load_portfolio_projects():
        for bucket, query, extra in plan:
            try:
                data = autonomy._gql(api_key, query, {"projectId": p["project_id"], **extra})
            except autonomy.LinearRateLimitError:
                raise
            except Exception as exc:  # noqa: BLE001
                errors.append(f"fetch_failed:{bucket}:{p['name']}:{type(exc).__name__}")
                continue
            for issue in (data.get("project") or {}).get("issues", {}).get("nodes") or []:
                iid = issue.get("id")
                if not iid or iid in seen[bucket]:
                    continue
                seen[bucket].add(iid)
                issue["_team_id"] = p["team_id"]
                buckets[bucket].append(issue)
    return buckets, errors


def label_names(issue: dict) -> set[str]:
    return {n.get("name", "").lower() for n in (issue.get("labels") or {}).get("nodes") or []}


def pr_refs(issue: dict) -> list[tuple[str, int]]:
    """GitHub PRs linked to the issue (attachments first, then description)."""
    texts = [a.get("url") or "" for a in (issue.get("attachments") or {}).get("nodes") or []]
    texts.append(issue.get("description") or "")
    refs: list[tuple[str, int]] = []
    for text in texts:
        for repo, num in _PR_URL_RE.findall(text):
            ref = (repo, int(num))
            if ref not in refs:
                refs.append(ref)
    return refs


def open_blockers(issue: dict) -> list[str]:
    """Identifiers of unfinished issues that block this one."""
    out = []
    for rel in (issue.get("inverseRelations") or {}).get("nodes") or []:
        other = rel.get("issue") or {}
        if rel.get("type") == "blocks" and (other.get("state") or {}).get("type") not in ("completed", "canceled"):
            out.append(other.get("identifier") or "?")
    return out


def github_get(path: str) -> dict | list:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise RuntimeError("GITHUB_TOKEN not set")
    req = urllib.request.Request(
        f"{_GITHUB_API}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Pi-CEO-TicketSweeper/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


_RED_CONCLUSIONS = {"failure", "timed_out", "cancelled", "action_required", "startup_failure"}


def pr_facts(repo: str, number: int) -> dict:
    """Facts needed to judge a PR: open?, red checks?, reviewed?, age."""
    pr = github_get(f"/repos/{repo}/pulls/{number}")
    sha = ((pr.get("head") or {}).get("sha")) or ""
    runs = github_get(f"/repos/{repo}/commits/{sha}/check-runs?per_page=100") if sha else {}
    reviews = github_get(f"/repos/{repo}/pulls/{number}/reviews?per_page=100")
    return {
        "open": pr.get("state") == "open" and not pr.get("merged"),
        "created_at": pr.get("created_at") or "",
        "red": any((r.get("conclusion") or "") in _RED_CONCLUSIONS for r in (runs or {}).get("check_runs") or []),
        "reviewed": bool(reviews),
    }
