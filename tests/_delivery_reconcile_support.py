"""tests/_delivery_reconcile_support.py — fakes for the RA-8100 delivery collector tests.

Nothing here touches the network. ``autonomy._gql``, ``ticket_sweeper_io.github_get``
and ``vercel_monitor._vercel_get`` are replaced (the pattern in
``tests/_ticket_sweeper_support.py``), and a spy on ``urllib.request.urlopen``
records any real request so a test can assert there were none. Values are fake.
"""
from __future__ import annotations

import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server import autonomy, autonomy_linear_rate, ticket_sweeper_io, vercel_monitor  # noqa: E402

API_KEY = "test-key"
SHA_A = "a" * 40
SHA_B = "b" * 40
PIDEV = "CleanExpo/Pi-Dev-Ops"
ATO = "CleanExpo/ATO"
ALLOWED = frozenset({"cleanexpo/pi-dev-ops", "cleanexpo/ato"})


class HTTP404(Exception):
    """Stands in for urllib.error.HTTPError(404) without building a response."""

    code = 404


def issue(identifier: str, url: str = "") -> dict:
    """A Linear issue node shaped like the mission query's result."""
    return {"id": f"id-{identifier}", "identifier": identifier, "state": {"type": "started"},
            "startedAt": "2026-11-14T00:00:00Z", "completedAt": None, "createdAt": "2026-11-13T00:00:00Z",
            "assignee": {"name": "Test Owner"}, "description": url,
            "attachments": {"pageInfo": {"hasNextPage": False}, "nodes": []}}


def linear_page(nodes: list[dict], next_cursor: str | None = None) -> dict:
    """One page of `project.issues`."""
    info = {"hasNextPage": next_cursor is not None, "endCursor": next_cursor}
    return {"project": {"issues": {"nodes": nodes, "pageInfo": info}}}


def open_pull(number: int, sha: str = SHA_A, user_type: str = "User") -> dict:
    """A pulls/{n} payload for an open PR."""
    return {"number": number, "state": "open", "merged": False, "merge_commit_sha": None,
            "draft": False, "created_at": "2026-11-14T01:00:00Z", "merged_at": None,
            "head": {"sha": sha}, "user": {"login": "someone", "type": user_type}}


def good_pr_paths(repo: str, number: int, sha: str = SHA_A) -> dict:
    """Every GET an open PR's evidence needs, answered well."""
    return {
        f"/repos/{repo}/pulls/{number}": open_pull(number, sha),
        f"/repos/{repo}/commits/{sha}": {"sha": sha},
        f"/repos/{repo}/commits/{sha}/check-runs?per_page=100&page=1": {
            "total_count": 1,
            "check_runs": [{"status": "completed", "conclusion": "success",
                            "completed_at": "2026-11-14T02:00:00Z"}]},
        f"/repos/{repo}/commits/{sha}/status": {"state": "success", "total_count": 0},
        f"/repos/{repo}/pulls/{number}/reviews?per_page=100&page=1": [],
    }


def install_fakes(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Fake Linear, GitHub, Vercel and cooldown; every call is logged."""
    st = SimpleNamespace(gql=[], github=[], vercel=[], net=[], gql_pages=[], gh={}, vc={},
                         limited=False, after_gql=None)

    def fake_gql(api_key: str, query: str, variables: dict | None = None, **_kw: object) -> object:
        st.gql.append((query, dict(variables or {})))
        if st.after_gql:
            st.after_gql(st)
        if not st.gql_pages:
            raise AssertionError("unexpected Linear request")
        page = st.gql_pages.pop(0)
        if isinstance(page, Exception):
            raise page
        return page

    def fake_github(path: str) -> object:
        st.github.append(path)
        value = st.gh.get(path, AssertionError(f"unexpected GitHub path {path}"))
        if isinstance(value, Exception):
            raise value
        return value

    def fake_vercel(path: str) -> object:
        st.vercel.append(path)
        value = st.vc.get("*", {"deployments": []})
        if isinstance(value, Exception):
            raise value
        return value

    def spy_urlopen(*args: object, **kwargs: object) -> None:
        st.net.append(args)
        raise AssertionError("real network call attempted")

    monkeypatch.setattr(urllib.request, "urlopen", spy_urlopen)
    monkeypatch.setattr(autonomy, "_gql", fake_gql)
    monkeypatch.setattr(ticket_sweeper_io, "github_get", fake_github)
    monkeypatch.setattr(vercel_monitor, "_vercel_get", fake_vercel)
    monkeypatch.setattr(autonomy_linear_rate, "linear_rate_limited", lambda: st.limited)
    return st


# ── Classifier builders (delivery_stage tests). Plain dicts shaped like the collector's output. ──
NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
SHA_C = "c" * 40
FAKE_REVIEWER = "fake-reviewer-one"


def ago(hours: float) -> str:
    """An ISO-8601 UTC string ``hours`` before NOW."""
    return (NOW - timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def mission(identifier: str = "RA-1", state: str = "started", *, started: float | None = 1,
            completed: float | None = None, owner: str | None = "Test Owner") -> dict:
    """A Linear mission node; the description carries a marker that must never be copied."""
    return {"id": f"id-{identifier}", "identifier": identifier, "state": {"type": state},
            "startedAt": None if started is None else ago(started),
            "completedAt": None if completed is None else ago(completed), "createdAt": ago(200),
            "assignee": {"name": owner} if owner else None, "description": "SECRET-DESCRIPTION-MARKER"}


def review(login: str | None, state: str, commit: str = SHA_A, at: float = 1) -> dict:
    return {"login": login, "state": state, "commit_id": commit, "submitted_at": ago(at)}


def open_facts(number: int = 7, *, repo: str = PIDEV, head: str = SHA_A, checks: str = "green",
               reviews: list[dict] | None = None, draft: bool = False, created: float = 80,
               check_done: float = 72) -> dict:
    """An open PR as ``pr_evidence`` returns it; checks: green, red, pending, none or status_only."""
    runs = {"green": [{"status": "completed", "conclusion": "success", "completed_at": ago(check_done)}],
            "red": [{"status": "completed", "conclusion": "failure", "completed_at": ago(check_done)}],
            "pending": [{"status": "in_progress", "conclusion": None, "completed_at": None}],
            "none": [], "status_only": []}[checks]
    status = {"state": "success", "total_count": 1} if checks == "status_only" else \
        {"state": "pending", "total_count": 0}
    return {"repo": repo, "number": number, "state": "open", "draft": draft, "created_at": ago(created),
            "merged_at": None, "head_sha": head, "merge_sha": None, "author_login": "someone",
            "author_type": "User", "check_runs": runs, "status": status, "reviews": list(reviews or [])}


def merged_facts(number: int = 7, *, repo: str = PIDEV, merge: str = SHA_B, merged: float = 30,
                 head: str = SHA_A) -> dict:
    return {"repo": repo, "number": number, "state": "merged", "draft": False, "created_at": ago(90),
            "merged_at": ago(merged), "head_sha": head, "merge_sha": merge, "author_login": "someone",
            "author_type": "User"}


def closed_facts(number: int = 8, *, repo: str = PIDEV) -> dict:
    return {"repo": repo, "number": number, "state": "closed", "draft": False, "created_at": ago(90),
            "merged_at": None, "head_sha": SHA_C, "merge_sha": None, "author_login": "someone",
            "author_type": "User"}


def error_item(number: int = 7, error: str = "unknown", reason: str = "http_500", *, repo: str = PIDEV,
               created: float | None = 10) -> dict:
    """What the tick builds when ``pr_evidence`` raised ``Unknown`` or ``MissingCommit``."""
    return {"repo": repo, "number": number, "error": error, "reason": reason,
            "created_at": None if created is None else ago(created)}


def orphan_item(number: int = 9, *, repo: str = PIDEV, author_type: str = "User", created: float = 72,
                head: str = SHA_C) -> dict:
    """One ``open_prs`` item plus its repo, for a PR no mission links."""
    return {"repo": repo, "number": number, "draft": False, "created_at": ago(created),
            "author_login": "someone", "author_type": author_type, "head_sha": head}
