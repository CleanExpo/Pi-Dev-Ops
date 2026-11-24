"""RA-8632: POST /api/telegram/linear/create obeys the Pi-Dev Linear contract.

Every Linear call is mocked through `telegram_proxy._linear_graphql`, the route's
single transport. The fake below keeps a small in-memory Linear (issues, labels,
projects) so dedup is exercised end to end: a second identical request must find
the issue the first one filed, not a canned answer.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.server.routes import telegram_proxy
from app.server.routes.telegram_proxy import LinearCreateBody, linear_create

_ROUTED = {"teamId": "team-default", "projectId": "proj-default"}
_FOOTER_RE = re.compile(
    r"\n---\n\*\*Pi-Dev-Ops run\*\*\n"
    r"- Run ID: `(?P<run_id>telegram-\d{8}T\d{6}Z-[0-9a-f]{8})`\n"
    r"- Source: Telegram /linear/create\n"
    r"- Filed: (?P<filed>\d{4}-\d{2}-\d{2})\Z"
)


class FakeLinear:
    """Minimal Linear: answers the queries the route sends, records every call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.issues: list[dict] = []
        self.labels: dict[str, list[dict]] = {}
        self.projects: list[dict] = []
        self.fail_on: str | None = None

    def ops(self, marker: str) -> list[dict]:
        return [v for q, v in self.calls if marker in q]

    def __call__(self, query: str, variables: dict | None = None) -> dict:
        variables = variables or {}
        self.calls.append((query, variables))
        if self.fail_on and self.fail_on in query:
            raise HTTPException(502, "Linear transport error: boom")
        if "FindOpenByTitle" in query:
            hits = [
                i for i in self.issues
                if i["teamId"] == variables["teamId"] and i["title"] == variables["title"] and i["open"]
            ]
            return {"issues": {"nodes": [_public(i) for i in hits[:1]]}}
        if "ProjectByName" in query:
            return {"projects": {"nodes": [p for p in self.projects if p["name"] == variables["name"]]}}
        if "issueLabelCreate" in query:
            inp = variables["input"]
            label = {"id": f"label-{len(self.labels) + 1}", "name": inp["name"]}
            self.labels.setdefault(inp["teamId"], []).append(label)
            return {"issueLabelCreate": {"success": True, "issueLabel": label}}
        if "labels(first: 100)" in query:
            return {"team": {"labels": {"nodes": self.labels.get(variables["teamId"], [])}}}
        if "issueCreate" in query:
            inp = variables["input"]
            n = len(self.issues) + 1
            issue = {"id": f"uuid-{n}", "identifier": f"RA-{9000 + n}", "url": f"https://linear.app/x/RA-{9000 + n}",
                     "title": inp["title"], "teamId": inp["teamId"], "open": True}
            self.issues.append(issue)
            return {"issueCreate": {"success": True, "issue": _public(issue)}}
        raise AssertionError(f"unexpected Linear query: {query}")


def _public(issue: dict) -> dict:
    return {k: issue[k] for k in ("id", "identifier", "url", "title")}


@pytest.fixture
def linear(monkeypatch) -> FakeLinear:
    fake = FakeLinear()
    fake.labels["team-default"] = [{"id": "label-src", "name": "pi-dev:source"}]
    monkeypatch.setattr(telegram_proxy, "_linear_graphql", fake)
    monkeypatch.setattr(telegram_proxy, "_project_routing", lambda project_id: dict(_ROUTED))
    return fake


def _post(**fields) -> dict:
    return asyncio.run(linear_create(LinearCreateBody(**fields)))


# ── 1. dedup: an open issue with the same title is returned, not duplicated ──

def test_existing_open_issue_is_returned_instead_of_created(linear):
    linear.issues.append({"id": "uuid-old", "identifier": "RA-1234", "url": "https://linear.app/x/RA-1234",
                          "title": "Fix the login page", "teamId": "team-default", "open": True})

    out = _post(title="Fix the login page")

    assert out["existing"] is True
    assert out["identifier"] == "RA-1234"
    assert linear.ops("issueCreate(") == []
    lookup_query = next(q for q, _ in linear.calls if "FindOpenByTitle" in q)
    # Same shape as swarm/margot_tools._lookup_open_issue: ID! comparator, open states only.
    assert "$teamId: ID!" in lookup_query
    for state_type in ("triage", "backlog", "unstarted", "started"):
        assert state_type in lookup_query
    assert "completed" not in lookup_query and "canceled" not in lookup_query
    assert linear.ops("FindOpenByTitle") == [{"teamId": "team-default", "title": "Fix the login page"}]


def test_new_title_is_created_and_marked_not_existing(linear):
    out = _post(title="Brand new task")
    assert out["existing"] is False
    assert len(linear.ops("issueCreate(")) == 1


# ── 2. the created issue carries pi-dev:source ───────────────────────────────

def test_created_issue_carries_source_label(linear):
    _post(title="Label me")
    (create,) = linear.ops("issueCreate(")
    assert create["input"]["labelIds"] == ["label-src"]


def test_source_label_is_created_when_team_lacks_it(linear):
    linear.labels.clear()
    _post(title="Label me too")
    (label_create,) = linear.ops("issueLabelCreate")
    assert label_create["input"]["name"] == "pi-dev:source"
    (create,) = linear.ops("issueCreate(")
    assert create["input"]["labelIds"] == [linear.labels["team-default"][0]["id"]]


def test_unresolvable_source_label_creates_nothing(linear):
    linear.labels.clear()
    linear.fail_on = "issueLabelCreate"
    with pytest.raises(HTTPException) as err:
        _post(title="No label available")
    assert err.value.status_code == 502
    assert linear.ops("issueCreate(") == []


# ── 3. the description ends with the contract footer ─────────────────────────

def test_description_ends_with_contract_footer(linear):
    out = _post(title="Footer check", description="Body text from Telegram.")
    (create,) = linear.ops("issueCreate(")
    description = create["input"]["description"]
    assert description.startswith("Body text from Telegram.\n")
    match = _FOOTER_RE.search(description)
    assert match, description
    assert match["filed"] == datetime.now(timezone.utc).date().isoformat()
    assert out["run_id"] == match["run_id"]


def test_footer_present_without_description_and_run_ids_unique(linear):
    _post(title="First")
    _post(title="Second")
    run_ids = []
    for create in linear.ops("issueCreate("):
        description = create["input"]["description"]
        match = _FOOTER_RE.search("\n" + description)
        assert match and description.startswith("---\n"), description
        run_ids.append(match["run_id"])
    assert len(set(run_ids)) == 2


# ── 4. Pattern B routing by repository name ──────────────────────────────────

@pytest.mark.parametrize("repo", ["CleanExpo/Pi-Dev-Ops", "Pi-Dev-Ops", "https://github.com/CleanExpo/Pi-Dev-Ops.git"])
def test_repo_routes_to_project_with_exact_name(linear, repo):
    linear.labels["team-pdo"] = [{"id": "label-pdo", "name": "pi-dev:source"}]
    linear.projects = [
        {"id": "proj-lower", "name": "pi-dev-ops", "teams": {"nodes": [{"id": "team-wrong"}]}},
        {"id": "proj-pdo", "name": "Pi-Dev-Ops", "teams": {"nodes": [{"id": "team-pdo"}]}},
    ]

    _post(title="Routed by repo", repo=repo)

    assert linear.ops("ProjectByName") == [{"name": "Pi-Dev-Ops"}]
    assert linear.ops("FindOpenByTitle")[0]["teamId"] == "team-pdo"
    (create,) = linear.ops("issueCreate(")
    assert create["input"]["projectId"] == "proj-pdo"
    assert create["input"]["teamId"] == "team-pdo"
    assert create["input"]["labelIds"] == ["label-pdo"]


def test_repo_without_exact_project_is_422_and_creates_nothing(linear):
    linear.projects = [{"id": "proj-lower", "name": "pi-dev-ops", "teams": {"nodes": [{"id": "team-x"}]}}]
    with pytest.raises(HTTPException) as err:
        _post(title="Nowhere to go", repo="CleanExpo/Pi-Dev-Ops")
    assert err.value.status_code == 422
    assert linear.ops("issueCreate(") == []
    assert linear.ops("FindOpenByTitle") == []


def test_no_repo_keeps_existing_routing(linear):
    _post(title="Default routing", project_id="restoreassist")
    assert linear.ops("ProjectByName") == []
    (create,) = linear.ops("issueCreate(")
    assert create["input"]["teamId"] == "team-default"
    assert create["input"]["projectId"] == "proj-default"


# ── idempotency and fail-closed ──────────────────────────────────────────────

def test_same_request_twice_creates_one_issue(linear):
    first = _post(title="Send twice", description="same body")
    second = _post(title="Send twice", description="same body")
    assert len(linear.ops("issueCreate(")) == 1
    assert first["existing"] is False and second["existing"] is True
    assert first["identifier"] == second["identifier"]


def test_failed_lookup_creates_nothing(linear):
    linear.fail_on = "FindOpenByTitle"
    with pytest.raises(HTTPException) as err:
        _post(title="Lookup is down")
    assert err.value.status_code == 502
    assert linear.ops("issueCreate(") == []
    assert linear.ops("issueLabelCreate") == []


def test_lookup_without_issue_list_creates_nothing(linear, monkeypatch):
    # An empty `data` must not read as "no duplicate" (silent blind filing).
    def empty_lookup(query, variables=None):
        if "FindOpenByTitle" in query:
            linear.calls.append((query, variables or {}))
            return {}
        return linear(query, variables)

    monkeypatch.setattr(telegram_proxy, "_linear_graphql", empty_lookup)
    with pytest.raises(HTTPException) as err:
        _post(title="Malformed lookup")
    assert err.value.status_code == 502
    assert linear.ops("issueCreate(") == []
