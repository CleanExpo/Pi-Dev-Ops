"""UNI-2648 — displayed queue is the claimable queue.

One eligibility function gates both Mission Control's dashboard snapshot and
the autonomy poller's fetch. An ineligible issue is neither shown nor claimed.
"""

from __future__ import annotations

import inspect
from unittest.mock import patch

import pytest

from app.server import autonomy
from app.server.autonomy_eligibility import (
    filter_claimable_issues,
    issue_is_claimable,
    queue_snapshot_from_issues,
)
from app.server.routes import mission_control

_PROJECT = "proj-alpha"
_REGISTRY = {_PROJECT}
_PROJECT_ROW = {
    "project_id": _PROJECT,
    "team_id": "team-a",
    "repo_url": "https://github.com/x/y",
    "name": "Alpha",
}


def _issue(
    *,
    identifier: str = "RA-1",
    title: str = "ship it",
    state_name: str = "Ready for Pi-Dev",
    state_type: str = "unstarted",
    labels: list[str] | None = None,
    project_id: str = _PROJECT,
    priority: int = 1,
    issue_id: str | None = None,
) -> dict:
    return {
        "id": issue_id or identifier,
        "identifier": identifier,
        "title": title,
        "priority": priority,
        "state": {"name": state_name, "type": state_type},
        "labels": {"nodes": [{"name": name} for name in (
            labels if labels is not None else ["pi-dev:autonomous"]
        )]},
        "project": {"id": project_id},
        "_project_id": project_id,
    }


_ELIGIBLE = _issue()
_TODO_UNSTARTED = _issue(
    identifier="RA-TODO", state_name="Todo", state_type="unstarted",
)
_NO_LABEL = _issue(identifier="RA-BARE", labels=[])
_OTHER_PROJECT = _issue(identifier="RA-OTHER", project_id="not-registered")
_MACHINE_SHIP = _issue(
    identifier="RA-SHIP", labels=["pi-dev:machine-ship"], priority=2,
)


# ── Helper: four axes ────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("issue", "expected"),
    [
        (_ELIGIBLE, True),
        (_MACHINE_SHIP, True),
        (_TODO_UNSTARTED, False),
        (_NO_LABEL, False),
        (_OTHER_PROJECT, False),
        (_issue(identifier="RA-TRIAGE", state_name="Triage", state_type="unstarted"), False),
    ],
    ids=[
        "eligible-autonomous",
        "eligible-machine-ship",
        "ineligible-todo-unstarted",
        "ineligible-no-label",
        "ineligible-other-project",
        "ineligible-triage-unstarted",
    ],
)
def test_issue_is_claimable_four_axes(issue: dict, expected: bool) -> None:
    assert issue_is_claimable(issue, registered_project_ids=_REGISTRY) is expected


def test_priority_axis_drops_unlabelled_when_filter_set() -> None:
    labelled = _issue(identifier="RA-Q2", labels=["pi-dev:autonomous", "q2-priority-1"])
    assert issue_is_claimable(
        labelled, registered_project_ids=_REGISTRY, priority_labels={"q2-priority-1"},
    )
    assert not issue_is_claimable(
        _ELIGIBLE, registered_project_ids=_REGISTRY, priority_labels={"q2-priority-1"},
    )


# ── Poller call site ─────────────────────────────────────────────────────────

def _gql_nodes(nodes: list[dict]):
    def fake_gql(_key: str, _query: str, _vars: dict | None = None) -> dict:
        return {"project": {"issues": {"nodes": [dict(n) for n in nodes]}}}
    return fake_gql


def test_fetch_todo_issues_keeps_eligible_drops_ineligible() -> None:
    mixed = [_ELIGIBLE, _TODO_UNSTARTED, _NO_LABEL, _OTHER_PROJECT, _MACHINE_SHIP]
    with patch.object(autonomy, "_load_portfolio_projects", return_value=[_PROJECT_ROW]), \
         patch.object(autonomy, "_gql", side_effect=_gql_nodes(mixed)), \
         patch.object(autonomy, "_PRIORITY_FILTER", set()):
        got = autonomy.fetch_todo_issues("k")
    assert [i["identifier"] for i in got] == ["RA-1", "RA-SHIP"]


def test_fetch_todo_issues_does_not_claim_unstarted_high_priority() -> None:
    """The abandoned dashboard filter (unstarted + priority<=2) must not leak in."""
    abandoned = _issue(
        identifier="RA-NOISE",
        state_name="Todo",
        state_type="unstarted",
        priority=1,
        labels=[],
    )
    with patch.object(autonomy, "_load_portfolio_projects", return_value=[_PROJECT_ROW]), \
         patch.object(autonomy, "_gql", side_effect=_gql_nodes([abandoned])), \
         patch.object(autonomy, "_PRIORITY_FILTER", set()):
        assert autonomy.fetch_todo_issues("k") == []


# ── Dashboard call site ──────────────────────────────────────────────────────

def test_queue_snapshot_displays_eligible_hides_ineligible(monkeypatch) -> None:
    monkeypatch.setenv("LINEAR_API_KEY", "k")
    mixed = [_ELIGIBLE, _TODO_UNSTARTED, _NO_LABEL, _OTHER_PROJECT, _MACHINE_SHIP]
    monkeypatch.setattr(autonomy, "fetch_todo_issues", lambda _key: mixed)
    monkeypatch.setattr(autonomy, "_load_portfolio_projects", lambda: [_PROJECT_ROW])
    monkeypatch.setattr(autonomy, "_PRIORITY_FILTER", set())
    snap = mission_control._queue_snapshot()
    assert snap["urgent"] == 1
    assert snap["high"] == 1
    assert snap["next_issue_id"] == "RA-1"
    assert snap["next_issue_title"] == "ship it"


def test_queue_snapshot_empty_when_only_ineligible(monkeypatch) -> None:
    monkeypatch.setenv("LINEAR_API_KEY", "k")
    monkeypatch.setattr(
        autonomy, "fetch_todo_issues",
        lambda _key: [_TODO_UNSTARTED, _NO_LABEL, _OTHER_PROJECT],
    )
    monkeypatch.setattr(autonomy, "_load_portfolio_projects", lambda: [_PROJECT_ROW])
    monkeypatch.setattr(autonomy, "_PRIORITY_FILTER", set())
    assert mission_control._queue_snapshot() == {
        "urgent": 0, "high": 0, "next_issue_id": None, "next_issue_title": "",
    }


def test_queue_snapshot_without_api_key_is_empty(monkeypatch) -> None:
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    assert mission_control._queue_snapshot()["next_issue_id"] is None


# ── Both call sites share the helper; old filter is gone ─────────────────────

def test_both_call_sites_use_the_same_eligibility_function() -> None:
    fetch_src = inspect.getsource(autonomy.fetch_todo_issues)
    queue_src = inspect.getsource(mission_control._queue_snapshot)
    assert "filter_claimable_issues" in fetch_src
    assert "filter_claimable_issues" in queue_src
    assert "unstarted" not in queue_src
    assert "priority: {eq:" not in queue_src


def test_filter_claimable_issues_matches_snapshot_shape() -> None:
    rows = filter_claimable_issues(
        [_ELIGIBLE, _TODO_UNSTARTED, _MACHINE_SHIP],
        registered_project_ids=_REGISTRY,
    )
    snap = queue_snapshot_from_issues(rows)
    assert snap["urgent"] == 1
    assert snap["high"] == 1
    assert snap["next_issue_id"] == "RA-1"
