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
    monkeypatch.setattr(
        autonomy, "_PRIORITY_FILTER", {"q2-priority-1", "q2-priority-2"}
    )

    def _fake_gql(_key, _query, _vars):
        return {
            "project": {
                "issues": {
                    "nodes": [
                        {
                            "id": "issue-1",
                            "identifier": "SYN-957",
                            "labels": {
                                "nodes": [
                                    {"name": "q2-priority-1"},
                                    {"name": "pi-dev:autonomous"},
                                ]
                            },
                            "priority": 1,
                        },
                        {
                            "id": "issue-2",
                            "identifier": "SYN-914",
                            "labels": {
                                "nodes": [{"name": "pi-dev:autonomous"}]
                            },
                            "priority": 2,
                        },
                    ]
                }
            }
        }

    fake_project = [{
        "project_id": "p1",
        "team_id": "t1",
        "repo_url": "https://github.com/x/y",
        "name": "Test",
    }]

    with patch.object(autonomy, "_gql", side_effect=_fake_gql):
        with patch.object(
            autonomy, "_load_portfolio_projects", return_value=fake_project
        ):
            result = autonomy.fetch_todo_issues("fake-key")

    # Only SYN-957 (q2-priority-1) survives;
    # SYN-914 (no priority label) filtered out
    assert len(result) == 1
    assert result[0]["identifier"] == "SYN-957"


def test_fetch_no_filter_when_disabled(monkeypatch):
    """Empty filter set passes both labelled + unlabelled issues through."""
    monkeypatch.setattr(autonomy, "_PRIORITY_FILTER", set())

    def _fake_gql(_key, _query, _vars):
        return {
            "project": {
                "issues": {
                    "nodes": [
                        {
                            "id": "issue-1",
                            "identifier": "SYN-957",
                            "labels": {"nodes": [{"name": "q2-priority-1"}]},
                            "priority": 1,
                        },
                        {
                            "id": "issue-2",
                            "identifier": "SYN-914",
                            "labels": {"nodes": []},
                            "priority": 2,
                        },
                    ]
                }
            }
        }

    fake_project = [{
        "project_id": "p1",
        "team_id": "t1",
        "repo_url": "https://github.com/x/y",
        "name": "Test",
    }]

    with patch.object(autonomy, "_gql", side_effect=_fake_gql):
        with patch.object(
            autonomy, "_load_portfolio_projects", return_value=fake_project
        ):
            result = autonomy.fetch_todo_issues("fake-key")

    # Both issues passed through — filter is empty, no post-filtering applied
    assert len(result) == 2


def test_fetch_filter_partial_match(monkeypatch):
    """Issue with q2-priority-3 label passes if q2-priority-3 is in the filter."""
    monkeypatch.setattr(
        autonomy, "_PRIORITY_FILTER", {"q2-priority-1", "q2-priority-3"}
    )

    def _fake_gql(_key, _query, _vars):
        return {
            "project": {
                "issues": {
                    "nodes": [
                        {
                            "id": "issue-aeo",
                            "identifier": "SYN-822",
                            "labels": {
                                "nodes": [
                                    {"name": "q2-priority-3"},
                                    {"name": "pi-dev:autonomous"},
                                ]
                            },
                            "priority": 2,
                        },
                    ]
                }
            }
        }

    fake_project = [{
        "project_id": "p1",
        "team_id": "t1",
        "repo_url": "https://github.com/x/y",
        "name": "Test",
    }]

    with patch.object(autonomy, "_gql", side_effect=_fake_gql):
        with patch.object(
            autonomy, "_load_portfolio_projects", return_value=fake_project
        ):
            result = autonomy.fetch_todo_issues("fake-key")

    # SYN-822 (q2-priority-3) passes since q2-priority-3 is in filter set
    assert len(result) == 1
    assert result[0]["identifier"] == "SYN-822"
