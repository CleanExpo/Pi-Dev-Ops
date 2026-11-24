"""RA-8632: routing and the parse layer of POST /api/telegram/linear/create.

Split from test_telegram_linear_create_contract.py (which holds the in-memory
fake Linear) to keep both files under the 300-line gate. Covers:
- Pattern B routing by repository name, built into a typed `Routing`;
- the one parse layer: every malformed Linear answer is 502 and files nothing;
- the one transport wrapper: any transport exception is 502.
"""
from __future__ import annotations

import re
from typing import Any

import pytest
from fastapi import HTTPException

from app.server.routes import telegram_proxy
from tests.test_telegram_linear_create_contract import _MARKERS, _ROUTED, FakeLinear, _post, _post_fails


@pytest.fixture
def linear(monkeypatch) -> FakeLinear:
    fake = FakeLinear()
    fake.labels["team-default"] = [{"id": "label-src", "name": "pi-dev:source"}]
    monkeypatch.setattr(telegram_proxy, "_linear_graphql", fake)
    monkeypatch.setattr(telegram_proxy, "_project_routing", lambda project_id: dict(_ROUTED))
    return fake


def _project(pid: str, name: str, *team_ids: str) -> dict:
    return {"id": pid, "name": name, "teams": {"nodes": [{"id": t} for t in team_ids]}}


# ── 4 / B. routing: Pattern B by repository name, typed Routing ──────────────

@pytest.mark.parametrize("repo", ["CleanExpo/Pi-Dev-Ops", "Pi-Dev-Ops", " Pi-Dev-Ops ",
                                  "https://github.com/CleanExpo/Pi-Dev-Ops.git",
                                  "https://github.com/CleanExpo/Pi-Dev-Ops/"])
def test_repo_routes_to_project_with_exact_name(linear, repo):
    linear.labels["team-pdo"] = [{"id": "label-pdo", "name": "pi-dev:source"}]
    linear.projects = [_project("proj-lower", "pi-dev-ops", "team-wrong"), _project("proj-pdo", "Pi-Dev-Ops", "team-pdo"),
                       _project("proj-other", "RestoreAssist", "team-other")]
    _post(title="Routed by repo", repo=repo)
    assert linear.ops("ProjectByName") == [{"name": "Pi-Dev-Ops"}]
    assert linear.ops("FindOpenByTitle")[0]["teamId"] == "team-pdo"
    (create,) = linear.ops("issueCreate(")
    assert (create["input"]["projectId"], create["input"]["teamId"]) == ("proj-pdo", "team-pdo")
    assert create["input"]["labelIds"] == ["label-pdo"]


def test_lowercase_repo_routes_to_lowercase_project_when_both_exist(linear):
    linear.labels["team-lower"] = [{"id": "label-lower", "name": "pi-dev:source"}]
    linear.projects = [_project("proj-pdo", "Pi-Dev-Ops", "team-pdo"), _project("proj-lower", "pi-dev-ops", "team-lower")]
    _post(title="Lowercase", repo="CleanExpo/pi-dev-ops")
    (create,) = linear.ops("issueCreate(")
    assert (create["input"]["projectId"], create["input"]["teamId"]) == ("proj-lower", "team-lower")


@pytest.mark.parametrize("projects", [
    [_project("proj-lower", "pi-dev-ops", "team-x")],                   # case variant only
    [_project("p1", "Pi-Dev-Ops", "team-a"), _project("p2", "Pi-Dev-Ops", "team-b")],  # two exact
    [_project("proj-pdo", "Pi-Dev-Ops", "team-a", "team-b")],           # two teams
    [_project("proj-pdo", "Pi-Dev-Ops")],                               # no team
])
def test_no_single_destination_is_422_and_creates_nothing(linear, projects):
    linear.projects = projects
    _post_fails(422, title="Nowhere to go", repo="CleanExpo/Pi-Dev-Ops")
    assert linear.ops("FindOpenByTitle") == []
    assert linear.ops("issueCreate(") == []


def test_no_repo_keeps_existing_routing(linear):
    _post(title="Default routing", project_id="restoreassist")
    assert linear.ops("ProjectByName") == []
    (create,) = linear.ops("issueCreate(")
    assert (create["input"]["teamId"], create["input"]["projectId"]) == ("team-default", "proj-default")


@pytest.mark.parametrize("repo", [
    "", "   ", "owner/", "/name", "not a repo", "a/b/c", "CleanExpo/Pi-Dev-Ops/tree/main",
    "https://github.com/CleanExpo/Pi-Dev-Ops/issues", "https://github.com/CleanExpo",
    "https://gitlab.com/CleanExpo/Pi-Dev-Ops", "git@github.com:CleanExpo/Pi-Dev-Ops.git",
    "..", "CleanExpo/..", "Clean_Expo/Pi-Dev-Ops", "Pi Dev Ops", "https://github.com/a/b?x=1",
])
def test_unusable_repo_is_422_and_touches_no_linear(linear, repo):
    _post_fails(422, title="Bad repo", repo=repo)
    assert linear.calls == []


@pytest.mark.parametrize("routing", [{"projectId": "p"}, {"teamId": "", "projectId": "p"},
                                     {"teamId": 7, "projectId": "p"}, {"teamId": "t", "projectId": 9}])
def test_malformed_default_routing_is_502_and_touches_no_linear(linear, monkeypatch, routing):
    monkeypatch.setattr(telegram_proxy, "_project_routing", lambda project_id: routing)
    _post_fails(502, title="Bad config")
    assert linear.calls == []


# ── A. one parse layer: every malformed answer is 502 and files nothing ──────

_ENVELOPES = [None, [], "oops", 7, {}]


def _list_shapes(key: str, inner: str | None = None) -> list:
    def wrap(nodes: Any) -> dict:
        return {key: {inner: {"nodes": nodes}}} if inner else {key: {"nodes": nodes}}
    shapes = [{key: None}, {key: []}, {key: "x"}, wrap(None), wrap("x"), wrap({}), wrap([None]), wrap(["x"]), wrap([7])]
    return shapes + ([{key: {inner: None}}] if inner else [])


_ISSUE = {"id": "u-1", "identifier": "RA-1", "url": "https://linear.app/x/RA-1", "title": "Malformed"}
_BAD_ISSUES = [{**_ISSUE, "id": 1}, {**_ISSUE, "id": ""}, {**_ISSUE, "identifier": None},
               {**_ISSUE, "url": None}, {**_ISSUE, "title": 5}] + [
    {k: v for k, v in _ISSUE.items() if k != drop} for drop in _ISSUE]
_PROJ = _project("proj-pdo", "Pi-Dev-Ops", "team-pdo")
_BAD_PROJECTS = [{**_PROJ, "id": None}, {**_PROJ, "id": 3}, {**_PROJ, "name": None},
                 {k: v for k, v in _PROJ.items() if k != "id"}, {k: v for k, v in _PROJ.items() if k != "teams"},
                 {**_PROJ, "teams": None}, {**_PROJ, "teams": {"nodes": [{}]}}, {**_PROJ, "teams": {"nodes": [{"id": 5}]}},
                 {**_PROJ, "teams": {"nodes": ["team-pdo"]}}]
_LABEL = {"id": "label-src", "name": "pi-dev:source"}
_BAD_LABELS = [{"name": "pi-dev:source"}, {**_LABEL, "id": 4}, {**_LABEL, "id": ""}, {"id": "label-src"}]


def _bad_create(key: str, item_key: str, good_item: dict, bad_items: list) -> list:
    shapes = [{key: {"success": s, item_key: good_item}} for s in ("yes", 1, "true", False, None)]
    shapes.append({key: {item_key: good_item}})
    shapes += [{key: {"success": True, item_key: item}} for item in [None, "x", *bad_items]]
    shapes.append({key: {"success": True}})
    return _ENVELOPES + [{key: None}, {key: "x"}] + shapes


_MALFORMED = (
    [("FindOpenByTitle", s) for s in _ENVELOPES + _list_shapes("issues")
     + [{"issues": {"nodes": [bad]}} for bad in _BAD_ISSUES]]
    + [("ProjectByName", s) for s in _ENVELOPES + _list_shapes("projects")
       + [{"projects": {"nodes": [bad]}} for bad in _BAD_PROJECTS]]
    + [("SourceLabel", s) for s in _ENVELOPES + _list_shapes("team", "labels")
       + [{"team": {"labels": {"nodes": [bad]}}} for bad in _BAD_LABELS]]
    + [("issueLabelCreate", s) for s in _bad_create("issueLabelCreate", "issueLabel", _LABEL, _BAD_LABELS)]
)


@pytest.mark.parametrize(("marker", "data"), _MALFORMED, ids=[f"{m}-{i}" for i, (m, _) in enumerate(_MALFORMED)])
def test_malformed_answer_is_502_and_creates_nothing(linear, marker, data):
    linear.projects = [_PROJ]
    linear.labels["team-pdo"] = [] if marker == "issueLabelCreate" else [dict(_LABEL)]
    if marker == "issueLabelCreate":
        linear.labels["team-default"] = []
    linear.raw[marker] = data
    _post_fails(502, title="Malformed", repo="Pi-Dev-Ops" if marker == "ProjectByName" else None)
    assert linear.ops("issueCreate(") == []


_BAD_CREATES = _bad_create("issueCreate", "issue", _ISSUE, _BAD_ISSUES)


@pytest.mark.parametrize("data", _BAD_CREATES, ids=[f"issueCreate-{i}" for i in range(len(_BAD_CREATES))])
def test_malformed_issue_create_is_502_naming_run_id(linear, data):
    linear.raw["issueCreate("] = data
    err = _post_fails(502, title="Phantom issue")
    (create,) = linear.ops("issueCreate(")
    run_id = re.search(r"Run ID: `([^`]+)`", create["input"]["description"])[1]
    assert run_id in err.detail and "may exist" in err.detail


@pytest.mark.parametrize("marker", _MARKERS)
@pytest.mark.parametrize("exc", [HTTPException(502, "boom"), HTTPException(401, "no key"), ValueError("bad json"),
                                 AttributeError("'list' object has no attribute 'get'"), KeyError("data")])
def test_any_transport_error_is_502_and_creates_nothing(linear, marker, exc):
    linear.projects = [_PROJ]
    linear.labels["team-pdo"] = [] if marker == "issueLabelCreate" else [dict(_LABEL)]
    linear.raise_on = (marker, exc)
    err = _post_fails(502, title="Transport", repo="Pi-Dev-Ops")
    created = linear.ops("issueCreate(")
    if marker == "issueCreate(":
        assert len(created) == 1 and "may exist" in err.detail
    else:
        assert created == []
