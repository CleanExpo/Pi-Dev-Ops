"""RA-7931: the autonomy queue is one paginated Linear read, not projects x labels.

The old poller read every portfolio project once per autonomy label (15 x 2 = 30+
requests a poll, 12 polls an hour). These pin the replacement: one query per page
whatever the project count, the same result set as the old loop, a partial read is
never the whole queue, and no top-level ``or`` (Linear ignored one in RA-7910).
"""
from __future__ import annotations

import re
from unittest.mock import patch

import pytest

from app.server import autonomy, autonomy_queue
from app.server.autonomy_portfolio import portfolio_issues
from app.server.autonomy_eligibility import IncompleteRead

_LABELS = ("pi-dev:autonomous", "pi-dev:machine-ship")
_PROJECTS = [
    {"project_id": f"proj-{n}", "team_id": f"team-{n}",
     "repo_url": f"https://github.com/acme/{n}", "name": n.title()}
    for n in ("alpha", "beta", "gamma", "delta")
]


def _node(n: int, project: str, labels: tuple[str, ...], state: str = "Ready for Pi-Dev") -> dict:
    return {
        "id": f"id-{n}", "identifier": f"RA-{n}", "title": "t", "priority": 1 + n % 3,
        "state": {"id": "s", "name": state, "type": "unstarted"},
        "labels": {"nodes": [{"name": x} for x in labels]},
        "project": {"id": project},
    }


def _fixture() -> list[dict]:
    """Ready and not-Ready issues over registered and unregistered projects and labels."""
    out, n = [], 0
    for project in ("proj-alpha", "proj-beta", "proj-gamma", "proj-delta", "proj-unregistered"):
        for labels in ((_LABELS[0],), (_LABELS[1],), _LABELS, ("bug",), ()):
            for state in ("Ready for Pi-Dev", "Todo"):
                n += 1
                out.append(_node(n, project, labels, state))
    return out


class _FakeLinear:
    """Applies the variables of whichever query arrives, and pages 10 nodes at a time."""

    def __init__(self, issues: list[dict]):
        self.issues, self.calls = issues, []

    def __call__(self, _key, query, variables=None):
        v = dict(variables or {})
        self.calls.append((query, v))
        projects = v.get("projectIds") or [v.get("projectId")]
        labels = v.get("labelNames") or [v.get("autonomyLabel")]
        hits = [dict(i, labels=dict(i["labels"])) for i in self.issues
                if i["project"]["id"] in projects and i["state"]["name"] == v["statusName"]
                and {x["name"] for x in i["labels"]["nodes"]} & set(labels)]
        start = int(v.get("after") or 0)
        page = hits[start:start + autonomy_queue.PAGE_SIZE]
        more = start + autonomy_queue.PAGE_SIZE < len(hits)
        conn = {"nodes": page, "pageInfo": {"hasNextPage": more,
                                            "endCursor": str(start + len(page)) if more else None}}
        return {"issues": conn} if "projectIds" in v else {"project": {"issues": conn}}


def _old_loop(gql, projects) -> list[dict]:
    """The pre-RA-7931 read, kept here as the reference result."""
    seen, merged = set(), []
    for p in projects:
        for label in _LABELS:
            after = None
            while True:
                d = gql("k", "old", {"projectId": p["project_id"], "statusName": "Ready for Pi-Dev",
                                     "autonomyLabel": label, "after": after})
                conn = d["project"]["issues"]
                for issue in conn["nodes"]:
                    if issue["id"] not in seen:
                        seen.add(issue["id"])
                        merged.append({**issue, "_team_id": p["team_id"], "_repo_url": p["repo_url"]})
                if not conn["pageInfo"]["hasNextPage"]:
                    break
                after = conn["pageInfo"]["endCursor"]
    return merged


def test_one_query_per_page_not_per_project_or_label():
    fake = _FakeLinear(_fixture() + [_node(1000 + i, "proj-alpha", (_LABELS[0],)) for i in range(15)])
    got = portfolio_issues(fake, "k", _PROJECTS, "Ready for Pi-Dev", _LABELS)
    # 12 Ready+labelled fixture issues on registered projects + 15 more = 27 -> 3 pages.
    assert len(got) == 27
    assert len(fake.calls) == 3
    assert all(q == autonomy_queue.TODO_ISSUES_QUERY for q, _ in fake.calls)
    assert fake.calls[0][1]["projectIds"] == [p["project_id"] for p in _PROJECTS]
    assert set(fake.calls[0][1]["labelNames"]) == set(_LABELS)


def test_same_result_set_as_the_old_per_project_loop():
    issues = _fixture()
    old_fake, new_fake = _FakeLinear(issues), _FakeLinear(issues)
    old = _old_loop(old_fake, _PROJECTS)
    new = portfolio_issues(new_fake, "k", _PROJECTS, "Ready for Pi-Dev", _LABELS)
    assert {i["identifier"] for i in new} == {i["identifier"] for i in old}
    assert len(new) == len({i["id"] for i in new})  # deduped: both-label issues once
    assert {(i["identifier"], i["_team_id"], i["_repo_url"]) for i in new} == \
        {(i["identifier"], i["_team_id"], i["_repo_url"]) for i in old}
    assert len(old_fake.calls) == len(_PROJECTS) * len(_LABELS)
    assert len(new_fake.calls) == 2  # 12 matches, 10 a page


def test_poller_fetch_uses_one_read_for_the_portfolio():
    fake = _FakeLinear(_fixture())
    with patch.object(autonomy, "_load_portfolio_projects", return_value=_PROJECTS), \
         patch.object(autonomy, "_gql", side_effect=fake), \
         patch.object(autonomy, "_PRIORITY_FILTER", set()):
        got = autonomy.fetch_todo_issues("k")
    assert len(fake.calls) == 2
    assert {i["_project_id"] for i in got} <= {p["project_id"] for p in _PROJECTS}
    assert len(got) == 12


@pytest.mark.parametrize("second_page", [
    {"issues": None},                                          # GraphQL error nulled the connection
    {"issues": {"nodes": None, "pageInfo": {}}},               # nodes unread
    {"issues": {"nodes": [], "pageInfo": {"hasNextPage": True}}},  # more pages, no cursor
], ids=["null-connection", "null-nodes", "no-cursor"])
def test_a_partial_read_is_never_the_whole_queue(second_page):
    first = {"issues": {"nodes": [_node(1, "proj-alpha", _LABELS)],
                        "pageInfo": {"hasNextPage": True, "endCursor": "c"}}}

    def gql(*_a):
        pages = iter([first, second_page])
        return lambda *_b: next(pages)

    with pytest.raises(IncompleteRead):
        portfolio_issues(gql(), "k", _PROJECTS, "Ready for Pi-Dev", _LABELS)
    with patch.object(autonomy, "_load_portfolio_projects", return_value=_PROJECTS), \
         patch.object(autonomy, "_gql", side_effect=gql()):
        assert autonomy.fetch_todo_issues("k") == []
    with patch.object(autonomy, "_load_portfolio_projects", return_value=_PROJECTS), \
         patch.object(autonomy, "_gql", side_effect=gql()), \
         pytest.raises(RuntimeError, match="portfolio scan failed"):
        autonomy.fetch_todo_issues("k", fail_on_error=True)


def test_a_runaway_cursor_is_refused():
    endless = {"issues": {"nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": "c"}}}
    calls = []

    def gql(*_a):
        calls.append(1)
        return endless

    with pytest.raises(IncompleteRead):
        portfolio_issues(gql, "k", _PROJECTS, "Ready for Pi-Dev", _LABELS)
    assert len(calls) == autonomy_queue.MAX_PAGES


def test_no_projects_means_no_request():
    calls = []
    assert portfolio_issues(lambda *a: calls.append(a), "k", [], "x", _LABELS) == []
    assert calls == []


def test_filter_has_no_top_level_or_and_uses_in_comparators():
    q = autonomy_queue.TODO_ISSUES_QUERY
    assert not re.search(r"\bor\s*:", q), "Linear silently ignored a top-level `or` (RA-7910)"
    assert "project: { id: { in: $projectIds } }" in q
    assert "labels: { name: { in: $labelNames } }" in q
    assert "state: { name: { eq: $statusName } }" in q
    assert "project(id:" not in q, "the per-project read is gone"
