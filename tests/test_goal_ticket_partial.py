"""Partial Goal → Linear writes: filed tickets must survive a later failure."""
from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.server.auth import require_auth, require_rate_limit
from app.server.goal_projects import create_project
from app.server.goal_ticket import file_drafts
from app.server.routes import goal_ticket as goal_ticket_route
from tests.test_goal_ticket import _FakeLinear, _SOURCE_LABEL


class _FailSecond(_FakeLinear):
    """First issueCreate succeeds. The next one fails so a batch can stop mid-file."""

    def __call__(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        if "issueCreate" in query and self.calls >= 1:
            return {"errors": [{"message": "Linear down after first ticket"}]}
        return super().__call__(query, variables)


@pytest.fixture
def goal_project(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    monkeypatch.setenv("GOAL_PROJECTS_PATH", str(tmp_path / "goal-projects.json"))
    return create_project(
        {
            "title": "Control Goal desk",
            "description": "Operators turn a stated goal into Linear tickets.",
            "audience": "Operators and engineers using Control.",
        }
    )


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(goal_ticket_route.router)
    app.dependency_overrides[require_auth] = lambda: None
    app.dependency_overrides[require_rate_limit] = lambda: None
    return TestClient(app)


def test_file_drafts_returns_partial_filed_when_later_ticket_fails() -> None:
    fake = _FailSecond()
    out = file_drafts(
        "CleanExpo/Pi-Dev-Ops",
        [
            {
                "title": "First ticket lands",
                "goal": "The first approved ticket exists in Linear",
                "acceptance": "RA-8001 exists in Backlog after the first write.",
            },
            {
                "title": "Second ticket fails",
                "goal": "The second approved ticket exists in Linear",
                "acceptance": "RA-8002 exists in Backlog after the second write.",
            },
        ],
        approved=True,
        parent_goal="File two tickets and stop if the second write fails",
        gql=fake,
    )
    assert out["error"] == "create_failed"
    assert out["failed_title"] == "Second ticket fails"
    assert len(out["filed"]) == 1
    assert out["filed"][0]["identifier"] == "RA-8001"
    assert len(fake.created) == 1


def _partial_file_result(error: str, **extra: Any) -> dict[str, Any]:
    return {
        "error": error,
        "filed": [
            {
                "identifier": "RA-8001",
                "url": "https://linear.app/unite-group/issue/RA-8001",
                "title": "First ticket lands",
                "state": "Backlog",
                "labels": [_SOURCE_LABEL],
            }
        ],
        **extra,
    }


def _post_file(client: TestClient, project_id: str) -> Any:
    return client.post(
        "/api/goal-ticket",
        json={
            "goal": "File two tickets and stop if the second write fails",
            "acceptance": "The first ticket remains visible after the second write fails.",
            "project_id": project_id,
            "approved": True,
            "tickets": [
                {
                    "title": "First ticket lands",
                    "goal": "The first approved ticket exists in Linear",
                    "acceptance": "RA-8001 exists in Backlog after the first write.",
                }
            ],
        },
    )


def test_file_route_returns_filed_tickets_on_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, goal_project: dict[str, str]
) -> None:
    monkeypatch.setattr(
        goal_ticket_route,
        "file_drafts",
        lambda *args, **kwargs: _partial_file_result(
            "create_failed", failed_title="Second ticket fails"
        ),
    )
    resp = _post_file(client, goal_project["id"])
    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert detail["failed_title"] == "Second ticket fails"
    assert detail["filed"][0]["identifier"] == "RA-8001"


def test_file_route_keeps_filed_on_validation_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, goal_project: dict[str, str]
) -> None:
    monkeypatch.setattr(
        goal_ticket_route,
        "file_drafts",
        lambda *args, **kwargs: _partial_file_result(
            "validation", fields=["goal"], failed_title="Short child"
        ),
    )
    resp = _post_file(client, goal_project["id"])
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["error"] == "validation"
    assert detail["filed"][0]["identifier"] == "RA-8001"
    assert detail["failed_title"] == "Short child"
