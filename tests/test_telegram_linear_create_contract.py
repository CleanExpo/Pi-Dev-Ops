"""RA-8632: POST /api/telegram/linear/create obeys the Pi-Dev Linear contract.

Every Linear call is mocked through `telegram_proxy._linear_graphql`, the route's
single transport. The fake keeps a small in-memory Linear and answers the way
Linear does, not the way the code hopes: `eq` filters are case-insensitive, so
project, label and title queries return case variants, and the project query
returns every project it holds. The code's own exact-match checks must reject
the near matches. Dedup is end to end: a second identical request must find the
issue the first one filed, not a canned answer.

Routing and malformed-answer tests live in test_telegram_linear_create_parsing.py
(split to keep each file under the 300-line gate); it imports the fake from here.
"""
from __future__ import annotations

import re
import threading
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi import HTTPException

from app.server import telegram_linear
from app.server.routes import telegram_proxy
from app.server.routes.telegram_proxy import LinearCreateBody, linear_create

_ROUTED = {"teamId": "team-default", "projectId": "proj-default"}
_FOOTER_RE = re.compile(
    r"\n---\n\*\*Pi-Dev-Ops run\*\*\n"
    r"- Run ID: `(?P<run_id>telegram-\d{8}T\d{6}Z-[0-9a-f]{8})`\n"
    r"- Source: Telegram /linear/create\n"
    r"- Filed: (?P<filed>\d{4}-\d{2}-\d{2})\Z"
)
# Just before UTC midnight: a test that re-read the wall clock would drift a day.
_FIXED_NOW = datetime(2026, 11, 24, 23, 59, 59, 999999, tzinfo=timezone.utc)
_MARKERS = ("FindOpenByTitle", "ProjectByName", "SourceLabel", "issueLabelCreate", "issueCreate(")


class FakeLinear:
    """Minimal Linear: answers the five queries the route sends, records every call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.issues: list[dict] = []
        self.labels: dict[str, list[dict]] = {}
        self.projects: list[dict] = []
        self.fail_on: str | None = None             # raise HTTPException on this query
        self.raise_on: tuple[str, BaseException] | None = None  # raise a non-HTTP error
        self.raw: dict[str, Any] = {}               # marker -> raw `data` to return verbatim
        self.pause_on: str | None = None            # hold this query until two overlap (or timeout)
        self._guard = threading.Lock()
        self._inside = 0
        self._overlap = threading.Event()

    def ops(self, marker: str) -> list[dict]:
        return [v for q, v in self.calls if marker in q]

    def _pause(self) -> None:
        with self._guard:
            self._inside += 1
            if self._inside >= 2:
                self._overlap.set()
        self._overlap.wait(timeout=0.5)

    def _answer(self, query: str, v: dict) -> Any:
        if "FindOpenByTitle" in query:
            hits = [i for i in self.issues if i["teamId"] == v["teamId"] and i["open"]
                    and i["title"].lower() == v["title"].lower()]
            return {"issues": {"nodes": [_public(i) for i in hits]}}
        if "ProjectByName" in query:
            return {"projects": {"nodes": list(self.projects)}}
        if "issueLabelCreate" in query:
            inp = v["input"]
            label = {"id": f"label-new-{sum(map(len, self.labels.values())) + 1}", "name": inp["name"]}
            self.labels.setdefault(inp["teamId"], []).append(label)
            return {"issueLabelCreate": {"success": True, "issueLabel": label}}
        if "SourceLabel" in query:
            team = self.labels.get(v["teamId"], [])
            return {"team": {"labels": {"nodes": [lb for lb in team if lb["name"].lower() == v["name"].lower()]}}}
        if "issueCreate(" in query:
            return self._create_issue(v["input"])
        raise AssertionError(f"unexpected Linear query: {query}")

    def _create_issue(self, inp: dict) -> dict:
        with self._guard:
            n = len(self.issues) + 1
            issue = {"id": f"uuid-{n}", "identifier": f"RA-{9000 + n}", "url": f"https://linear.app/x/RA-{9000 + n}",
                     "title": inp["title"], "teamId": inp["teamId"], "open": True}
            self.issues.append(issue)
        return {"issueCreate": {"success": True, "issue": _public(issue)}}

    def __call__(self, query: str, variables: dict | None = None) -> Any:
        variables = variables or {}
        self.calls.append((query, variables))
        if self.pause_on and self.pause_on in query:
            self._pause()
        if self.fail_on and self.fail_on in query:
            raise HTTPException(502, "Linear transport error: boom")
        if self.raise_on and self.raise_on[0] in query:
            raise self.raise_on[1]
        for marker, data in self.raw.items():
            if marker in query:
                return data
        return self._answer(query, variables)


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
    return linear_create(LinearCreateBody(**fields))


def _post_fails(status: int, **fields) -> HTTPException:
    with pytest.raises(HTTPException) as err:
        _post(**fields)
    assert err.value.status_code == status, err.value.detail
    return err.value


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
    assert linear.ops("FindOpenByTitle") == [{"teamId": "team-default", "projectId": "proj-default", "title": "Fix the login page"}]


def test_case_variant_title_is_not_a_duplicate(linear):
    linear.issues.append({"id": "uuid-old", "identifier": "RA-1234", "url": "https://linear.app/x/RA-1234",
                          "title": "fix the login page", "teamId": "team-default", "open": True})
    out = _post(title="Fix the login page")
    assert out["existing"] is False
    assert len(linear.ops("issueCreate(")) == 1


def test_new_title_is_created_and_marked_not_existing(linear):
    out = _post(title="Brand new task")
    assert out["existing"] is False
    assert out["url"] and out["title"] == "Brand new task"
    assert len(linear.ops("issueCreate(")) == 1


# ── 2. the created issue carries pi-dev:source ───────────────────────────────

def test_created_issue_carries_source_label(linear):
    _post(title="Label me")
    (create,) = linear.ops("issueCreate(")
    assert create["input"]["labelIds"] == ["label-src"]


def test_source_label_is_created_when_team_lacks_it(linear):
    linear.labels["team-default"] = [{"id": "label-near", "name": "Pi-Dev:Source"}]  # case variant only
    _post(title="Label me too")
    (label_create,) = linear.ops("issueLabelCreate")
    assert label_create["input"]["name"] == "pi-dev:source"
    (create,) = linear.ops("issueCreate(")
    assert create["input"]["labelIds"] == [linear.labels["team-default"][1]["id"]]


def test_label_found_beyond_first_100_is_reused_not_recreated(linear):
    others = [{"id": f"label-{n}", "name": f"other-{n}"} for n in range(150)]
    linear.labels["team-default"] = others + [{"id": "label-src", "name": "pi-dev:source"}]
    _post(title="Big label set")
    assert linear.ops("issueLabelCreate") == []
    (create,) = linear.ops("issueCreate(")
    assert create["input"]["labelIds"] == ["label-src"]
    assert linear.ops("SourceLabel") == [{"teamId": "team-default", "name": "pi-dev:source"}]


def test_created_label_with_wrong_name_is_502_and_creates_nothing(linear):
    linear.labels.clear()
    linear.raw["issueLabelCreate"] = {"issueLabelCreate": {"success": True,
                                                           "issueLabel": {"id": "l-x", "name": "pi-dev:autonomous"}}}
    _post_fails(502, title="Wrong label back")
    assert linear.ops("issueCreate(") == []


# ── 3. the description ends with the contract footer ─────────────────────────

def test_description_ends_with_contract_footer(linear):
    routing = telegram_linear.Routing(team_id="team-default", project_id="proj-default")
    out = telegram_linear.create_or_reuse(
        linear, routing=routing, title="Footer check", description="Body text from Telegram.",
        priority=2, now=_FIXED_NOW,
    )
    (create,) = linear.ops("issueCreate(")
    description = create["input"]["description"]
    assert description.startswith("Body text from Telegram.\n")
    match = _FOOTER_RE.search(description)
    assert match, description
    assert match["filed"] == "2026-11-24"
    assert match["run_id"].startswith("telegram-20261124T235959Z-")
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


# Routing (point 4 / class B) and the parse layer (class A) are in
# test_telegram_linear_create_parsing.py, which reuses the fake above.


# ── idempotency, fail-closed, races ──────────────────────────────────────────

def test_same_request_twice_creates_one_issue(linear):
    first = _post(title="Send twice", description="same body")
    second = _post(title="Send twice", description="same body")
    assert len(linear.ops("issueCreate(")) == 1
    assert first["existing"] is False and second["existing"] is True
    assert first["identifier"] == second["identifier"]


def test_failed_lookup_creates_nothing(linear):
    linear.fail_on = "FindOpenByTitle"
    _post_fails(502, title="Lookup is down")
    assert linear.ops("issueCreate(") == [] and linear.ops("issueLabelCreate") == []


def test_label_read_failure_is_502_and_creates_no_label_or_issue(linear):
    linear.fail_on = "SourceLabel"
    _post_fails(502, title="Label read down")
    assert linear.ops("issueLabelCreate") == [] and linear.ops("issueCreate(") == []


def _race(linear: FakeLinear, titles: list[str]) -> list[dict]:
    """Send each title on its own thread at once; return results, fail on any error.

    This exercises the in-process LOCK. In production the route is a plain `def`,
    so FastAPI runs concurrent requests on its worker threads, as these do.
    """
    results: list[dict] = []
    errors: list[BaseException] = []

    def send(title: str) -> None:
        try:
            results.append(_post(title=title, description="race"))
        except BaseException as exc:  # noqa: BLE001 - surfaced by the assert below
            errors.append(exc)

    threads = [threading.Thread(target=send, args=(t,)) for t in titles]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert errors == []
    return results


def test_concurrent_identical_requests_create_one_issue(linear):
    linear.pause_on = "FindOpenByTitle"
    results = _race(linear, ["Same moment", "Same moment"])
    assert len(linear.ops("issueCreate(")) == 1
    assert sorted(r["existing"] for r in results) == [False, True]
    assert results[0]["identifier"] == results[1]["identifier"]


def test_concurrent_different_titles_create_one_source_label(linear):
    linear.labels.clear()
    linear.pause_on = "SourceLabel"
    _race(linear, ["Title one", "Title two"])
    assert len(linear.ops("issueLabelCreate")) == 1
    label_ids = {c["input"]["labelIds"][0] for c in linear.ops("issueCreate(")}
    assert label_ids == {linear.labels["team-default"][0]["id"]}
