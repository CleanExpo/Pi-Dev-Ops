"""RA-8646: every Linear list the Telegram filer reads is read to its last page.

The release review of RA-8632 found the same defect five times: the open-issue,
project and source-label lookups each asked for `first: 50` and read one page.
An exact match on page two was missed, so the filer duplicated an open issue,
refused a real project, or created a second `pi-dev:source` label.

The fix is one reader (`_every_node`) that every list goes through, and a
required `pageInfo` in the answer models. The last test pins the design: any
query constant that pages must take `$after` and ask for `pageInfo`.

The fake pages like Linear does (50 per page, opaque cursor, case-insensitive
`eq` near-misses fill page one), so a reader that stops early goes red.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

import pytest
from fastapi import HTTPException

from app.server import telegram_linear
from app.server.routes import telegram_proxy
from app.server.routes.telegram_proxy import LinearCreateBody, linear_create

_TITLE = "Fix the login page"
_PAGE_SIZE = 50
_ROUTED = {"teamId": "team-1", "projectId": "proj-1"}


class PagingLinear:
    """Holds full lists and serves them one page of 50 at a time."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.issues: list[dict] = []
        self.projects: list[dict] = []
        self.labels: list[dict] = []
        self.broken_cursor: str | None = None  # "null" or "repeat" to simulate a bad page chain

    def ops(self, marker: str) -> list[dict]:
        return [v for q, v in self.calls if marker in q]

    def _page(self, items: list[dict], v: dict) -> dict:
        start = int(v.get("after") or 0)
        end = start + _PAGE_SIZE
        more = end < len(items)
        cursor: str | None = str(end) if more else None
        if more and self.broken_cursor == "null":
            cursor = None
        if more and self.broken_cursor == "repeat":
            cursor = str(_PAGE_SIZE)
        return {"nodes": items[start:end], "pageInfo": {"hasNextPage": more, "endCursor": cursor}}

    def __call__(self, query: str, variables: dict | None = None) -> Any:
        v = variables or {}
        self.calls.append((query, v))
        if "FindOpenByTitle" in query:
            hits = [i for i in self.issues if i["title"].lower() == v["title"].lower()]
            return {"issues": self._page(hits, v)}
        if "ProjectByName" in query:
            hits = [p for p in self.projects if p["name"].lower() == v["name"].lower()]
            return {"projects": self._page(hits, v)}
        if "SourceLabel" in query:
            hits = [lb for lb in self.labels if lb["name"].lower() == v["name"].lower()]
            return {"team": {"labels": self._page(hits, v)}}
        if "issueLabelCreate" in query:
            label = {"id": f"label-new-{len(self.labels)}", "name": v["input"]["name"]}
            self.labels.append(label)
            return {"issueLabelCreate": {"success": True, "issueLabel": label}}
        if "issueCreate(" in query:
            n = len(self.issues) + 1
            issue = {"id": f"uuid-{n}", "identifier": f"RA-{9000 + n}",
                     "url": f"https://linear.app/x/RA-{9000 + n}", "title": v["input"]["title"]}
            self.issues.append(issue)
            return {"issueCreate": {"success": True, "issue": issue}}
        raise AssertionError(f"unexpected Linear query: {query}")


def _issue(n: int, title: str) -> dict:
    return {"id": f"u-{n}", "identifier": f"RA-{n}", "url": f"https://linear.app/x/RA-{n}", "title": title}


def _near_miss(n: int, text: str) -> str:
    """A case variant of `text` that Linear's `eq` would also return; never equal to it."""
    flips = [i for i, ch in enumerate(text) if ch.isalpha()]
    chars = list(text)
    for bit, i in enumerate(flips):
        if (n + 1) >> bit & 1:
            chars[i] = chars[i].swapcase()
    variant = "".join(chars)
    assert variant != text
    return variant


def _project(pid: str, name: str, *teams: str) -> dict:
    return {"id": pid, "name": name, "teams": {"nodes": [{"id": t} for t in teams]}}


@pytest.fixture
def linear(monkeypatch) -> PagingLinear:
    fake = PagingLinear()
    fake.labels = [{"id": "label-src", "name": "pi-dev:source"}]
    monkeypatch.setattr(telegram_proxy, "_linear_graphql", fake)
    monkeypatch.setattr(telegram_proxy, "_project_routing", lambda project_id: dict(_ROUTED))
    return fake


def _post(**fields: Any) -> dict:
    return asyncio.run(linear_create(LinearCreateBody(**{"title": _TITLE, **fields})))


def _post_fails(status: int, **fields: Any) -> None:
    with pytest.raises(HTTPException) as caught:
        _post(**fields)
    assert caught.value.status_code == status


def test_open_issue_on_second_page_is_reused_not_duplicated(linear):
    linear.issues = [_issue(n, _near_miss(n, _TITLE)) for n in range(_PAGE_SIZE)] + [_issue(999, _TITLE)]

    out = _post()

    assert out["existing"] is True and out["identifier"] == "RA-999"
    assert linear.ops("issueCreate(") == []
    assert [v.get("after") for v in linear.ops("FindOpenByTitle")] == [None, "50"]


def test_exact_project_on_second_page_is_routed(linear):
    linear.projects = [_project(f"p-{n}", _near_miss(n, "Pi-Dev-Ops"), "team-x") for n in range(_PAGE_SIZE)]
    linear.projects.append(_project("proj-pdo", "Pi-Dev-Ops", "team-pdo"))

    _post(repo="CleanExpo/Pi-Dev-Ops")

    (create,) = linear.ops("issueCreate(")
    assert (create["input"]["projectId"], create["input"]["teamId"]) == ("proj-pdo", "team-pdo")


def test_two_exact_projects_split_across_pages_are_still_refused(linear):
    linear.projects = [_project("p-first", "Pi-Dev-Ops", "team-a")]
    linear.projects += [_project(f"p-{n}", _near_miss(n, "Pi-Dev-Ops"), "team-x") for n in range(_PAGE_SIZE)]
    linear.projects.append(_project("p-second", "Pi-Dev-Ops", "team-b"))

    _post_fails(422, repo="CleanExpo/Pi-Dev-Ops")

    assert linear.ops("issueCreate(") == []


def test_source_label_on_second_page_is_reused_not_recreated(linear):
    linear.labels = [{"id": f"l-{n}", "name": _near_miss(n, "pi-dev:source")} for n in range(_PAGE_SIZE)]
    linear.labels.append({"id": "label-src", "name": "pi-dev:source"})

    _post()

    assert linear.ops("issueLabelCreate") == []
    (create,) = linear.ops("issueCreate(")
    assert create["input"]["labelIds"] == ["label-src"]


@pytest.mark.parametrize("broken", ["null", "repeat"])
def test_unusable_next_page_cursor_is_502_and_files_nothing(linear, broken):
    linear.broken_cursor = broken
    linear.issues = [_issue(n, _near_miss(n, _TITLE)) for n in range(3 * _PAGE_SIZE)]

    _post_fails(502)

    assert linear.ops("issueCreate(") == []


def test_answer_without_page_info_is_502_and_files_nothing(linear, monkeypatch):
    def no_page_info(query: str, variables: dict | None = None) -> Any:
        answer = linear(query, variables)  # every other call answers normally, so a lax reader would file
        if "FindOpenByTitle" in query:
            return {"issues": {"nodes": answer["issues"]["nodes"]}}
        return answer

    monkeypatch.setattr(telegram_proxy, "_linear_graphql", no_page_info)

    _post_fails(502)

    assert linear.ops("issueCreate(") == []


@pytest.mark.parametrize("repo", ["CleanExpo/Pi-Dev-Ops.git", "Pi-Dev-Ops.git", "https://github.com/CleanExpo/Pi-Dev-Ops.git"])
def test_dot_git_suffix_is_dropped_in_every_repo_form(repo):
    assert telegram_linear.repo_name(repo) == "Pi-Dev-Ops"


@pytest.mark.parametrize("repo", [".git", "CleanExpo/.git", "CleanExpo/..git"])
def test_repo_that_is_only_a_dot_git_suffix_is_refused(repo):
    assert telegram_linear.repo_name(repo) == ""


_NESTED_ALLOWED = re.compile(r"teams\(first: 5\)")  # one team versus several is all routing reads


def test_every_paged_query_takes_after_and_asks_for_page_info():
    """Design guard: a new lookup cannot page with `first:` and read one page."""
    queries = {name: value for name, value in vars(telegram_linear).items()
               if isinstance(value, str) and value.startswith("query ")}
    paged = {name: q for name, q in queries.items() if "first:" in _NESTED_ALLOWED.sub("", q)}
    assert len(paged) == 4, sorted(paged)  # issues team-wide, issues in project, projects, labels
    assert paged, "positive control: the module's paged queries were not found"
    for name, query in paged.items():
        assert "$after: String" in query and "after: $after" in query, name
        assert "pageInfo { hasNextPage endCursor }" in query, name
