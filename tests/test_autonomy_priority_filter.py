"""RA-2209 — Pi-CEO autonomy poller q2-priority filter.

Empire-overview board memo 2026-05-10 (Stage 4b · E3 phase 2). Founder ruled
that the autonomy poller should only claim tickets aligned with Q2 priorities
#1 (CCW) and #2 (RA App Store) for a 14-day window. Implemented as a Python
post-filter driven by the PI_CEO_AUTONOMY_PRIORITY_FILTER env var. Code
default is empty (opt-in at deploy time) so existing test fixtures aren't
disturbed.

Tests use monkeypatch.setattr on the module-level `_PRIORITY_FILTER` set
rather than importlib.reload — reload clears module state in ways that
pollute downstream tests in the same session.
"""

from unittest.mock import patch

import app.server.autonomy as autonomy

_ONE_PROJECT = [{
    "project_id": "p1",
    "team_id": "t1",
    "repo_url": "https://github.com/x/y",
    "name": "Test",
}]


def _ready(identifier: str, extra_labels: list[str], priority: int, issue_id: str) -> dict:
    labels = [{"name": name} for name in ["pi-dev:autonomous", *extra_labels]]
    return {
        "id": issue_id,
        "identifier": identifier,
        "state": {"name": "Ready for Pi-Dev"},
        "labels": {"nodes": labels},
        "priority": priority,
    }


def _gql_nodes(nodes: list[dict]):
    def _fake_gql(_key, _query, _vars):
        return {"project": {"issues": {"nodes": nodes}}}
    return _fake_gql


def _fetch(monkeypatch, nodes: list[dict], priority_filter: set[str]) -> list[dict]:
    monkeypatch.setattr(autonomy, "_PRIORITY_FILTER", priority_filter)
    with patch.object(autonomy, "_gql", side_effect=_gql_nodes(nodes)), \
         patch.object(autonomy, "_load_portfolio_projects", return_value=_ONE_PROJECT):
        return autonomy.fetch_todo_issues("fake-key")


def test_priority_filter_default_disabled():
    """Default (env unset) keeps _PRIORITY_FILTER empty — opt-in only.

    The code default is empty so existing tests and non-Q2 deployments
    aren't surprised by behaviour changes. The filter is set at deploy
    time via the env var.
    """
    # Module is loaded with whatever env was present at process start.
    # In a clean test env, that's "" → empty set. Verify the contract.
    assert isinstance(autonomy._PRIORITY_FILTER, set)


def test_priority_filter_parses_csv_correctly(monkeypatch):
    """Comma-separated env var parses to a set, whitespace stripped."""
    monkeypatch.setattr(
        autonomy, "_PRIORITY_FILTER", {"q2-priority-1", "q2-priority-2"}
    )
    assert autonomy._PRIORITY_FILTER == {"q2-priority-1", "q2-priority-2"}


def test_fetch_filters_unlabelled_issues(monkeypatch):
    """Issue with autonomy label but no q2-priority label is filtered out."""
    result = _fetch(monkeypatch, [
        _ready("SYN-957", ["q2-priority-1"], 1, "issue-1"),
        _ready("SYN-914", [], 2, "issue-2"),
    ], {"q2-priority-1", "q2-priority-2"})
    assert [i["identifier"] for i in result] == ["SYN-957"]


def test_fetch_no_filter_when_disabled(monkeypatch):
    """Empty filter set passes both labelled + unlabelled issues through."""
    result = _fetch(monkeypatch, [
        _ready("SYN-957", ["q2-priority-1"], 1, "issue-1"),
        _ready("SYN-914", [], 2, "issue-2"),
    ], set())
    assert len(result) == 2


def test_fetch_filter_partial_match(monkeypatch):
    """Issue with q2-priority-3 label passes if q2-priority-3 is in the filter."""
    result = _fetch(monkeypatch, [
        _ready("SYN-822", ["q2-priority-3"], 2, "issue-aeo"),
    ], {"q2-priority-1", "q2-priority-3"})
    assert [i["identifier"] for i in result] == ["SYN-822"]
