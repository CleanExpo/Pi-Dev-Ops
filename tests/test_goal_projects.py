"""Goal project briefs — create and list, no GitHub."""
from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.server.auth import require_auth, require_rate_limit
from app.server import goal_projects as store
from app.server.goal_projects import (
    GoalProjectStoreError,
    create_project,
    get_project,
    load_projects,
    validate_brief,
)
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


def test_create_project_writes_supabase_not_a_local_file(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GOAL_PROJECTS_PATH", raising=False)
    dummy = tmp_path / "goal-projects.json"
    written: list[dict[str, str]] = []

    def fake_insert(row: dict[str, str]) -> dict[str, str]:
        written.append(row)
        return row

    monkeypatch.setattr(store, "_db_configured", lambda: True)
    monkeypatch.setattr(store, "_db_insert", fake_insert)
    row = create_project(
        {
            "title": "Saved looks workspace",
            "description": "Shoppers save looks from the feed.",
            "audience": "Shoppers on Synthex.",
        }
    )
    assert written[0]["id"] == row["id"]
    assert not dummy.exists()


def test_create_project_fails_when_database_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOAL_PROJECTS_PATH", raising=False)
    monkeypatch.setattr(store, "_db_configured", lambda: False)

    def boom(row: dict[str, str]) -> dict[str, str]:
        raise GoalProjectStoreError(
            "supabase_not_configured",
            "Supabase is not configured, so the project was not stored.",
        )

    monkeypatch.setattr(store, "_db_insert", boom)
    with pytest.raises(GoalProjectStoreError, match="not stored"):
        create_project(
            {
                "title": "Saved looks workspace",
                "description": "Shoppers save looks from the feed.",
                "audience": "Shoppers on Synthex.",
            }
        )


def test_load_projects_reads_supabase(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOAL_PROJECTS_PATH", raising=False)
    monkeypatch.setattr(store, "_db_configured", lambda: True)
    monkeypatch.setattr(
        store,
        "_db_select",
        lambda params: [
            {
                "id": "p1",
                "title": "Saved looks workspace",
                "description": "Shoppers save looks from the feed.",
                "audience": "Shoppers on Synthex.",
                "problem": "",
                "users": "",
                "outcomes": "",
                "constraints": "",
                "out_of_scope": "",
                "created_at": "2026-08-27T00:00:00Z",
            }
        ],
    )
    rows = load_projects()
    assert rows[0]["id"] == "p1"


def test_route_returns_503_when_database_write_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOAL_PROJECTS_PATH", raising=False)
    monkeypatch.setattr(store, "_db_configured", lambda: True)

    def boom(row: dict[str, str]) -> dict[str, str]:
        raise GoalProjectStoreError(
            "supabase_write_failed",
            "Project was not stored in the database.",
        )

    monkeypatch.setattr(store, "_db_insert", boom)
    app = FastAPI()
    app.include_router(goal_ticket_route.router)
    app.dependency_overrides[require_auth] = lambda: None
    app.dependency_overrides[require_rate_limit] = lambda: None
    client = TestClient(app)
    resp = client.post(
        "/api/goal-projects",
        json={
            "title": "Saved looks workspace",
            "description": "Shoppers save looks from the feed.",
            "audience": "Shoppers on Synthex.",
        },
    )
    assert resp.status_code == 503
    assert resp.json()["detail"]["error"] == "supabase_write_failed"
