"""tests/_delivery_reconcile_support.py — fakes for the RA-8100 delivery collector tests.

Nothing here touches the network. ``autonomy._gql``, ``ticket_sweeper_io.github_get``
and ``vercel_monitor._vercel_get`` are replaced (the pattern in
``tests/_ticket_sweeper_support.py``), and a spy on ``urllib.request.urlopen``
records any real request so a test can assert there were none. Values are fake.
"""
from __future__ import annotations

import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from _delivery_stored_support import PIDEV, refusal, stored, summary_of, tick_summary  # noqa: F401 — re-exported

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server import autonomy, autonomy_linear_rate, ticket_sweeper_io, vercel_monitor  # noqa: E402

API_KEY = "test-key"
SHA_A = "a" * 40
SHA_B = "b" * 40
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
            "check_runs": [{"id": 1, "status": "completed", "conclusion": "success",
                            "completed_at": "2026-11-14T02:00:00Z", "head_sha": sha}]},
        f"/repos/{repo}/commits/{sha}/status": {"state": "pending", "total_count": 0, "sha": sha},
        f"/repos/{repo}/pulls/{number}/reviews?per_page=100&page=1": [],
    }


_LIST_OWNER = re.compile(r"/repos/([^/]+/[^/]+)/pulls(?:\?state=open|/(\d+)/reviews\?)")


def _named_project(page: object, project: object) -> object:
    """A real answer names the project asked (``project.id``); a page built without one gets it here.
    A page that sets ``id`` itself (a mismatch test) is returned as built."""
    if isinstance(page, dict) and isinstance(page.get("project"), dict) and "id" not in page["project"]:
        return {**page, "project": {"id": project, **page["project"]}}
    return page


def _named_items(path: str, value: object) -> object:
    """A real open-pull list names each pull's base repo and a review list each review's pull; items built
    without those fields get the ones asked for here. An item that sets the field itself is kept as built."""
    match = _LIST_OWNER.match(path)
    if not match or not isinstance(value, list):
        return value
    repo, number = match.groups()
    field, named = (("pull_request_url", f"https://api.github.com/repos/{repo}/pulls/{number}") if number
                    else ("base", {"repo": {"full_name": repo}}))
    return [{field: named, **item} if isinstance(item, dict) else item for item in value]


def install_fakes(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Fake Linear, GitHub, Vercel and cooldown; every call is logged."""
    st = SimpleNamespace(gql=[], github=[], vercel=[], net=[], gql_pages=[], gh={}, vc={},
                         limited=False, after_gql=None, name_asked=True, name_project=True)

    def fake_gql(api_key: str, query: str, variables: dict | None = None, **_kw: object) -> object:
        st.gql.append((query, dict(variables or {})))
        if st.after_gql:
            st.after_gql(st)
        if not st.gql_pages:
            raise AssertionError("unexpected Linear request")
        page = st.gql_pages.pop(0)
        if isinstance(page, Exception):
            raise page
        return _named_project(page, (variables or {}).get("projectId")) if st.name_project else page

    def fake_github(path: str) -> object:
        st.github.append(path)
        value = st.gh.get(path, AssertionError(f"unexpected GitHub path {path}"))
        if isinstance(value, Exception):
            raise value
        return _named_items(path, value) if st.name_asked else value

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


# ── Tick builders (delivery_reconcile tick tests). A fake registry file, sweep paths and PR payloads. ──
def reg_entry(pid: str, repo: str, *, queryable: bool = True, vercel: str | None = None) -> dict:
    """One registry entry; fake identifiers only."""
    out: dict = {"id": pid, "repo": repo}
    if queryable:
        out.update({"linear_project_id": f"proj-{pid}", "linear_team_id": "team-fake"})
    if vercel:
        out["vercel_project_id"] = vercel
    return out


def sweep_path(repo: str) -> str:
    return f"/repos/{repo}/pulls?state=open&per_page=100&page=1"


def pr_paths(repo: str, number: int, sha: str = SHA_A, *, created: float = 80, check_done: float = 72) -> dict:
    """Every GET an open PR's evidence needs: checks green ``check_done`` hours before NOW, no review."""
    return {
        f"/repos/{repo}/pulls/{number}": {**open_pull(number, sha), "created_at": ago(created)},
        f"/repos/{repo}/commits/{sha}": {"sha": sha},
        f"/repos/{repo}/commits/{sha}/check-runs?per_page=100&page=1": {
            "total_count": 1,
            "check_runs": [{"id": 1, "status": "completed", "conclusion": "success", "completed_at": ago(check_done),
                            "head_sha": sha}]},
        f"/repos/{repo}/commits/{sha}/status": {"state": "pending", "total_count": 0, "sha": sha},
        f"/repos/{repo}/pulls/{number}/reviews?per_page=100&page=1": [],
    }


def merged_pull(number: int, merge: str = SHA_B, merged: float = 30) -> dict:
    """A pulls/{n} payload for a merged PR."""
    return {**open_pull(number), "state": "closed", "merged": True, "merge_commit_sha": merge,
            "merged_at": ago(merged), "created_at": ago(90)}


def merged_paths(repo: str, number: int, merge: str = SHA_B, merged: float = 30) -> dict:
    """Every GET a merged PR's evidence needs: the pull and a readable merge commit."""
    return {f"/repos/{repo}/pulls/{number}": merged_pull(number, merge, merged),
            f"/repos/{repo}/commits/{merge}": {"sha": merge}}


def compare_answer(base: str, head: str, status: str) -> dict:
    """A compare answer as GitHub gives it for ``status``: counts, commit list and merge base all agree."""
    commits = [{"sha": head}] if status in ("ahead", "diverged") else []
    fork = {"identical": base, "ahead": base, "behind": head, "diverged": "f" * 40}[status]
    return {"status": status, "base_commit": {"sha": base}, "merge_base_commit": {"sha": fork}, "commits": commits,
            "total_commits": len(commits), "ahead_by": len(commits), "behind_by": int(status in ("behind", "diverged"))}


def tick_issue(identifier: str, refs: tuple[tuple[str, int], ...] = (), *, links_whole: bool = True,
               extra: str = "", **kw: object) -> dict:
    """A mission node whose description links ``refs``; ``links_whole`` False leaves attachments unread."""
    node = mission(identifier, **kw)  # type: ignore[arg-type]
    urls = " ".join(f"https://github.com/{repo}/pull/{n}" for repo, n in refs)
    node["description"] = f"SECRET-DESCRIPTION-MARKER {urls} {extra}".strip()
    node["attachments"] = {"pageInfo": {"hasNextPage": not links_whole}, "nodes": []}
    return node


def setup_tick(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, entries: list[dict] | None) -> SimpleNamespace:
    """Fakes installed, a fake registry (None keeps the real one), the fake key, a tmp state path."""
    import json

    from app.server import config_loader
    from app.server import delivery_reconcile as dr

    st = install_fakes(monkeypatch)
    if entries is not None:
        reg = tmp_path / "projects.json"
        reg.write_text(json.dumps({"projects": entries}), encoding="utf-8")
        monkeypatch.setattr(config_loader, "PROJECTS_JSON", reg)
    monkeypatch.setenv("LINEAR_API_KEY", API_KEY)
    for name in ("RAILWAY_GIT_COMMIT_SHA", "BUILD_REVISION", "TAO_DELIVERY_RECONCILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(dr, "_last_save_ok", None)
    monkeypatch.setattr(dr, "_last_tick_error", None, raising=False)
    st.path = tmp_path / "state.json"
    return st


def run(st: SimpleNamespace, now: datetime = NOW) -> dict:
    """One tick through the public entry; a crash inside the tick fails the test, never passes it."""
    from app.server import delivery_reconcile as dr

    out = dr.run_reconcile_tick(now=now, path=str(st.path))
    assert not str(out.get("error", "")).startswith("tick_failed_"), out
    return out
