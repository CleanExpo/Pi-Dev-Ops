"""RA-8632: the duplicate lookup is scoped to the routed Linear project.

A same-title open issue in a sibling project of the same team must not be
returned as "existing"; the request files a new issue in its own project.
With no project in the routing, the lookup stays team-wide.

The fake applies the filters the query actually sends, so a lookup that drops
the project filter returns the sibling issue, as real Linear would.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.server.routes import telegram_proxy
from app.server.routes.telegram_proxy import LinearCreateBody, linear_create

_TITLE = "Fix the login page"


class ProjectAwareLinear:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.issues: list[dict] = []

    def __call__(self, query: str, variables: dict | None = None) -> Any:
        v = variables or {}
        self.calls.append((query, v))
        if "FindOpenByTitle" in query:
            scoped = "project:" in query
            hits = [i for i in self.issues
                    if i["teamId"] == v["teamId"] and i["title"] == v["title"]
                    and (not scoped or i["projectId"] == v["projectId"])]
            return {"issues": {"nodes": [_public(i) for i in hits]}}
        if "SourceLabel" in query:
            return {"team": {"labels": {"nodes": [{"id": "label-src", "name": "pi-dev:source"}]}}}
        if "issueCreate(" in query:
            inp = v["input"]
            n = len(self.issues) + 1
            issue = {"id": f"uuid-{n}", "identifier": f"RA-{9000 + n}", "url": f"https://linear.app/x/RA-{9000 + n}",
                     "title": inp["title"], "teamId": inp["teamId"], "projectId": inp.get("projectId")}
            self.issues.append(issue)
            return {"issueCreate": {"success": True, "issue": _public(issue)}}
        raise AssertionError(f"unexpected Linear query: {query}")


def _public(issue: dict) -> dict:
    return {k: issue[k] for k in ("id", "identifier", "url", "title")}


def _route(monkeypatch, routing: dict) -> ProjectAwareLinear:
    fake = ProjectAwareLinear()
    fake.issues.append({"id": "uuid-a", "identifier": "RA-1", "url": "https://linear.app/x/RA-1",
                        "title": _TITLE, "teamId": "team-1", "projectId": "proj-a"})
    monkeypatch.setattr(telegram_proxy, "_linear_graphql", fake)
    monkeypatch.setattr(telegram_proxy, "_project_routing", lambda project_id: dict(routing))
    return fake


def _post() -> dict:
    return asyncio.run(linear_create(LinearCreateBody(title=_TITLE)))


def test_same_title_in_sibling_project_is_not_a_duplicate(monkeypatch):
    fake = _route(monkeypatch, {"teamId": "team-1", "projectId": "proj-b"})

    out = _post()

    assert out["existing"] is False
    assert out["identifier"] != "RA-1"
    created = [v["input"] for q, v in fake.calls if "issueCreate(" in q]
    assert len(created) == 1 and created[0]["projectId"] == "proj-b"


def test_same_title_in_routed_project_is_returned(monkeypatch):
    fake = _route(monkeypatch, {"teamId": "team-1", "projectId": "proj-a"})

    out = _post()

    assert out["existing"] is True
    assert out["identifier"] == "RA-1"
    assert [q for q, _ in fake.calls if "issueCreate(" in q] == []


@pytest.mark.parametrize("project_id", [None, ""])
def test_no_project_in_routing_keeps_team_wide_lookup(monkeypatch, project_id):
    fake = _route(monkeypatch, {"teamId": "team-1", "projectId": project_id})

    out = _post()

    assert out["existing"] is True
    lookup = next(q for q, _ in fake.calls if "FindOpenByTitle" in q)
    assert "project:" not in lookup
