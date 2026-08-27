"""Goal project briefs — create and list, no GitHub."""
from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.server.auth import require_auth, require_rate_limit
from app.server.goal_projects import create_project, get_project, validate_brief
from app.server.routes import goal_ticket as goal_ticket_route


@pytest.fixture
def client(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("GOAL_PROJECTS_PATH", str(tmp_path / "goal-projects.json"))
    app = FastAPI()
    app.include_router(goal_ticket_route.router)
    app.dependency_overrides[require_auth] = lambda: None
    app.dependency_overrides[require_rate_limit] = lambda: None
    return TestClient(app)


def test_validate_brief_requires_title_description_audience() -> None:
    assert validate_brief({"title": "x", "description": "y", "audience": "z"}) == [
        "title",
        "description",
        "audience",
    ]
    assert validate_brief(
        {
            "title": "Saved looks workspace",
            "description": "Shoppers save looks from the feed.",
            "audience": "Shoppers on Synthex.",
        }
    ) == []


def test_create_and_get_project(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOAL_PROJECTS_PATH", str(tmp_path / "goal-projects.json"))
    row = create_project(
        {
            "title": "Saved looks workspace",
            "description": "Shoppers save looks from the feed.",
            "audience": "Shoppers on Synthex.",
            "problem": "Looks disappear after refresh.",
        }
    )
    loaded = get_project(row["id"])
    assert loaded is not None
    assert loaded["title"] == "Saved looks workspace"
    assert loaded["problem"] == "Looks disappear after refresh."


def test_route_creates_and_lists_projects(client: TestClient) -> None:
    created = client.post(
        "/api/goal-projects",
        json={
            "title": "Saved looks workspace",
            "description": "Shoppers save looks from the feed.",
            "audience": "Shoppers on Synthex.",
        },
    )
    assert created.status_code == 200
    project = created.json()["project"]
    assert project["id"]
    listed = client.get("/api/goal-projects")
    assert listed.status_code == 200
    assert listed.json()["projects"][0]["id"] == project["id"]
