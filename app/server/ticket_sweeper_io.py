"""ticket_sweeper_io.py — Linear queries and GitHub PR facts for the nightly
ticket sweeper (``ticket_sweeper.py``). Read-only; the writes live in
``ticket_sweeper_write.py``.

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
    labels(first: 100) { pageInfo { hasNextPage } nodes { name } }
    attachments(first: 100) { pageInfo { hasNextPage } nodes { url } }
    inverseRelations(first: 50) { pageInfo { hasNextPage } nodes { type issue { identifier state { type } } } }
"""

_PAGE = "first: 50, after: $cursor) { pageInfo { hasNextPage endCursor } nodes { %s } }"
_MAX_PAGES = 20  # 1,000 issues per bucket per project; beyond that the run is marked truncated

_STARTED_QUERY = """
query SweeperStarted($projectId: String!, $before: DateTimeOrDuration!, $cursor: String) {
    project(id: $projectId) {
        issues(filter: {
            state: { type: { eq: "started" } }
            updatedAt: { lt: $before }
        }, %s
    }
}
""" % (_PAGE % _ISSUE_FIELDS)

_IN_REVIEW_QUERY = """
query SweeperInReview($projectId: String!, $cursor: String) {
    project(id: $projectId) {
        issues(filter: { state: { name: { eq: "In Review" } } }, %s
    }
}
""" % (_PAGE % _ISSUE_FIELDS)

# A failed build lands in Todo (session_linear: failed → Todo). Filter on the
# state NAME: "Ready for Pi-Dev" is also type unstarted, and a retry waiting
# there must not be re-judged. Look back a week so a skipped night loses nothing.
_COMMENTS = "    comments(first: 100) { pageInfo { hasNextPage } nodes { body createdAt } }\n"

_RECENT_TODO_QUERY = """
query SweeperRecentTodo($projectId: String!, $since: DateTimeOrDuration!, $cursor: String) {
    project(id: $projectId) {
        issues(filter: {
            state: { name: { eq: "Todo" } }
            updatedAt: { gt: $since }
        }, %s
    }
}
""" % (_PAGE % (_ISSUE_FIELDS + _COMMENTS))

# Single-issue re-read: before any write (the ticket may have changed since the
# bucket fetch) and after it (a mutation helper returning is not proof it stuck).
_ISSUE_QUERY = "query SweeperIssue($id: String!) { issue(id: $id) { %s } }" % (_ISSUE_FIELDS + _COMMENTS)


def _iso_days_ago(days: int, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return (now - timedelta(days=days)).isoformat()


def _fetch_all(api_key: str, query: str, variables: dict) -> list[dict]:
    """Every page of one bucket for one project. Raises on a missing project or
    issues connection, and on more pages than _MAX_PAGES — never a silent short read."""
    nodes: list[dict] = []
    cursor = None
    for _ in range(_MAX_PAGES):
        data = autonomy._gql(api_key, query, {**variables, "cursor": cursor})
        conn = (data.get("project") or {}).get("issues")
        page = conn.get("pageInfo") if isinstance(conn, dict) else None
        if not isinstance(conn.get("nodes") if page else None, list) or not isinstance(page.get("hasNextPage"), bool):
            raise LookupError("project, issues connection, nodes or pageInfo missing")
        if not all(isinstance(n, dict) and n.get("id") and n.get("identifier") for n in conn["nodes"]):
            raise LookupError("malformed issue node")
        nodes.extend(conn["nodes"])
        if not page["hasNextPage"]:
            return nodes
        cursor = page.get("endCursor")
        if not isinstance(cursor, str) or not cursor:
            raise LookupError("hasNextPage without endCursor")
    raise OverflowError(f"more than {_MAX_PAGES} pages")


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
        ("recent_todo", _RECENT_TODO_QUERY, {"since": _iso_days_ago(7, now)}),
    )
    projects = autonomy._load_portfolio_projects()
    if not projects:
        errors.append("no_portfolio_projects")
    for p in projects:
        for bucket, query, extra in plan:
            try:
                nodes = _fetch_all(api_key, query, {"projectId": p["project_id"], **extra})
            except autonomy.LinearRateLimitError:
                raise
            except Exception as exc:  # noqa: BLE001
                errors.append(f"fetch_failed:{bucket}:{p['name']}:{type(exc).__name__}")
                continue
            for issue in nodes:
                iid = issue.get("id")
                if not iid or iid in seen[bucket]:
                    continue
                seen[bucket].add(iid)
                issue["_team_id"] = p["team_id"]
                buckets[bucket].append(issue)
    return buckets, errors


def fetch_issue(api_key: str, issue_id: str) -> dict:
    issue = autonomy._gql(api_key, _ISSUE_QUERY, {"id": issue_id}).get("issue")
    if not isinstance(issue, dict) or issue.get("id") != issue_id:
        raise LookupError("issue re-read failed")
    return issue


def label_names(issue: dict) -> set[str] | None:
    """Lower-cased label names, or None when the label list did not arrive whole."""
    nodes = complete_nodes(issue, "labels")
    return None if nodes is None else {(n.get("name") or "").lower() for n in nodes}


def pr_refs(issue: dict) -> list[tuple[str, int]] | None:
    """GitHub PRs linked to the issue (attachments, then description), or None
    when the attachment list did not arrive whole."""
    nodes = complete_nodes(issue, "attachments")
    if nodes is None:
        return None
    texts = [a.get("url") or "" for a in nodes]
    texts.append(issue.get("description") or "")
    refs: list[tuple[str, int]] = []
    for text in texts:
        for repo, num in _PR_URL_RE.findall(text):
            ref = (repo, int(num))
            if ref not in refs:
                refs.append(ref)
    return refs


def complete_nodes(issue: dict, key: str) -> list[dict] | None:
    """The connection's nodes, or None unless it provably arrived whole and well-formed."""
    conn = issue.get(key)
    if not isinstance(conn, dict) or (conn.get("pageInfo") or {}).get("hasNextPage") is not False:
        return None
    nodes = conn.get("nodes")
    if not isinstance(nodes, list) or not all(isinstance(n, dict) for n in nodes):
        return None
    return nodes


def open_blockers(issue: dict) -> list[str]:
    """Identifiers of unfinished issues that block this one. A relation list
    that did not arrive whole counts as blocked ("?unread"): never move on a guess."""
    nodes = complete_nodes(issue, "inverseRelations")
    if nodes is None:
        return ["?unread"]
    out = []
    for rel in nodes:
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


def _all_check_runs(repo: str, sha: str) -> list[dict]:
    """Every check run on the head; raises rather than return a partial list."""
    runs: list[dict] = []
    for page in range(1, 11):
        data = github_get(f"/repos/{repo}/commits/{sha}/check-runs?per_page=100&page={page}")
        batch, total = data.get("check_runs"), data.get("total_count")
        if not isinstance(batch, list) or not isinstance(total, int):
            raise LookupError("malformed check-runs payload")
        runs.extend(batch)
        if len(runs) >= total or not batch:
            if len(runs) < total:
                raise LookupError("check runs ended short of total_count")
            return runs
    raise OverflowError("more than 1,000 check runs")


def pr_facts(repo: str, number: int) -> dict:
    """Facts needed to judge a PR: open?, red checks?, reviewed?, age. Raises
    when an open PR's check state cannot be read, so the caller says 'unknown'."""
    pr = github_get(f"/repos/{repo}/pulls/{number}")
    sha = ((pr.get("head") or {}).get("sha")) or ""
    is_open = pr.get("state") == "open" and not pr.get("merged")
    if not is_open:
        return {"open": False, "created_at": "", "red": False, "reviewed": False}
    if not sha:
        raise LookupError("open PR without head sha")
    runs = _all_check_runs(repo, sha)
    # Commit statuses are a separate red signal from check runs (older CI, Vercel).
    status = github_get(f"/repos/{repo}/commits/{sha}/status")
    if not isinstance(status, dict) or "state" not in status:
        raise LookupError("malformed commit status payload")
    reviews = github_get(f"/repos/{repo}/pulls/{number}/reviews?per_page=100")
    red_runs = any((r.get("conclusion") or "") in _RED_CONCLUSIONS for r in runs)
    return {
        "open": True,
        "created_at": pr.get("created_at") or "",
        "red": red_runs or status["state"] in ("failure", "error"),
        "reviewed": bool(reviews),
    }


def state_is(issue: dict, name: str) -> bool:
    return ((issue.get("state") or {}).get("name") or "").lower() == name.lower()
