"""Goal → Linear ticket: required fields, Backlog only, no autonomy markers."""
from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.server.auth import require_auth, require_rate_limit
from app.server.goal_ticket import (
    _AUTONOMY_LABEL,
    _READY_STATE,
    _SOURCE_LABEL,
    build_description,
    file_goal,
    normalize_repo,
    resolve_project,
    title_from_goal,
    validate_goal,
)
from app.server.routes import goal_ticket as goal_ticket_route


PI_DEV_OPS_LINEAR_PROJECT = "f45212be-3259-4bfb-89b1-54c122c939a7"
PI_DEV_OPS_TEAM = "a8a52f07-63cf-4ece-9ad2-3e3bd3c15673"


def test_normalize_repo_accepts_url_and_slug() -> None:
    assert normalize_repo("https://github.com/CleanExpo/Pi-Dev-Ops.git") == "CleanExpo/Pi-Dev-Ops"
    assert normalize_repo("CleanExpo/Pi-Dev-Ops") == "CleanExpo/Pi-Dev-Ops"
    assert normalize_repo("not-a-repo") == ""


def test_validate_goal_requires_all_three_fields() -> None:
    assert validate_goal("", "CleanExpo/Pi-Dev-Ops", "ticket exists in Linear") == ["goal"]
    assert validate_goal("File this as a Linear ticket", "", "ticket exists") == ["repo"]
    assert validate_goal("File this as a Linear ticket", "CleanExpo/Pi-Dev-Ops", "x") == [
        "acceptance",
    ]
    assert validate_goal(
        "File this as a Linear ticket",
        "CleanExpo/Pi-Dev-Ops",
        "A Linear issue exists with this goal.",
    ) == []


def test_resolve_project_pins_pi_dev_ops_not_margot() -> None:
    project = resolve_project("CleanExpo/Pi-Dev-Ops")
    assert project is not None
    assert project["registry_id"] == "pi-dev-ops"
    assert project["project_id"] == PI_DEV_OPS_LINEAR_PROJECT
    assert project["team_id"] == PI_DEV_OPS_TEAM
    assert project["project_id"] != "94da87f8-a2a5-4fbb-9903-0047ff84d92c"


def test_description_carries_goal_repo_acceptance() -> None:
    body = build_description(
        "Add a README smoke line",
        "CleanExpo/Pi-Dev-Ops",
        "PR exists with that line.",
    )
    assert "## Goal" in body
    assert "Add a README smoke line" in body
    assert "`CleanExpo/Pi-Dev-Ops`" in body
    assert "PR exists with that line." in body
    assert _READY_STATE not in body
    assert _AUTONOMY_LABEL not in body


class _FakeLinear:
    """Captures issueCreate input. Serves Backlog + source label lookups."""

    def __init__(self) -> None:
        self.created: dict[str, Any] | None = None

    def __call__(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        q = query.replace(" ", "")
        if "team(id:$id){states" in q:
            return {
                "data": {
                    "team": {
                        "states": {
                            "nodes": [
                                {"id": "state-backlog", "name": "Backlog", "type": "backlog"},
                                {"id": "state-ready", "name": _READY_STATE, "type": "unstarted"},
                            ]
                        }
                    }
                }
            }
        if "labels(first:100)" in q or "labels(first: 100)" in query:
            return {
                "data": {
                    "team": {
                        "labels": {
                            "nodes": [
                                {"id": "label-source", "name": _SOURCE_LABEL},
                                {"id": "label-auto", "name": _AUTONOMY_LABEL},
                            ]
                        }
                    }
                }
            }
        if "issueCreate" in query:
            self.created = (variables or {}).get("input")
            return {
                "data": {
                    "issueCreate": {
                        "success": True,
                        "issue": {
                            "id": "issue-1",
                            "identifier": "RA-8000",
                            "title": title_from_goal("File this as a Linear ticket now"),
                            "url": "https://linear.app/unite-group/issue/RA-8000",
                        },
                    }
                }
            }
        return {"error": "unexpected_query", "query": query}


def test_file_goal_creates_backlog_without_autonomy_markers() -> None:
    fake = _FakeLinear()
    out = file_goal(
        "File this as a Linear ticket now",
        "https://github.com/CleanExpo/Pi-Dev-Ops",
        "RA-xxxx exists in Backlog with this goal.",
        gql=fake,
    )
    assert out["status"] == "created"
    assert out["identifier"] == "RA-8000"
    assert out["url"].endswith("RA-8000")
    assert out["state"] == "Backlog"
    assert _AUTONOMY_LABEL not in out["labels"]
    assert _SOURCE_LABEL in out["labels"]
    assert fake.created is not None
    assert fake.created["projectId"] == PI_DEV_OPS_LINEAR_PROJECT
    assert fake.created["teamId"] == PI_DEV_OPS_TEAM
    assert fake.created["stateId"] == "state-backlog"
    assert fake.created["stateId"] != "state-ready"
    assert fake.created["labelIds"] == ["label-source"]
    assert _AUTONOMY_LABEL not in fake.created["description"]
    assert _READY_STATE not in fake.created["description"]


def test_file_goal_rejects_unknown_repo() -> None:
    out = file_goal(
        "Something worth building today",
        "Acme/Not-In-Registry",
        "A ticket would exist if this repo were known.",
        gql=_FakeLinear(),
    )
    assert out["error"] == "unknown_repo"


def test_file_goal_rejects_short_fields() -> None:
    out = file_goal("short", "CleanExpo/Pi-Dev-Ops", "nope", gql=_FakeLinear())
    assert out["error"] == "validation"
    assert "goal" in out["fields"]
    assert "acceptance" in out["fields"]


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(goal_ticket_route.router)
    app.dependency_overrides[require_auth] = lambda: None
    app.dependency_overrides[require_rate_limit] = lambda: None
    return TestClient(app)


def test_route_returns_ticket_url(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_file(goal: str, repo: str, acceptance: str) -> dict[str, Any]:
        assert "Linear" in goal
        return {
            "status": "created",
            "identifier": "RA-8001",
            "url": "https://linear.app/unite-group/issue/RA-8001",
            "title": goal,
            "state": "Backlog",
            "labels": [_SOURCE_LABEL],
        }

    monkeypatch.setattr(goal_ticket_route, "file_goal", fake_file)
    resp = client.post(
        "/api/goal-ticket",
        json={
            "goal": "File this as a Linear ticket now",
            "repo": "CleanExpo/Pi-Dev-Ops",
            "acceptance": "Ticket RA-8001 exists in Linear Backlog.",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["identifier"] == "RA-8001"
    assert body["url"].endswith("RA-8001")
    assert body["state"] == "Backlog"
    assert _AUTONOMY_LABEL not in body["labels"]


def test_route_rejects_empty_body(client: TestClient) -> None:
    resp = client.post("/api/goal-ticket", json={"goal": "", "repo": "", "acceptance": ""})
    assert resp.status_code == 422
