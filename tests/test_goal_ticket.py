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
    file_drafts,
    file_goal,
    normalize_repo,
    resolve_project,
    title_from_goal,
    validate_goal,
)
from app.server.goal_analyze import analyze_goal, drafts_from_payload, fallback_drafts
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
        self.created: list[dict[str, Any]] = []
        self.calls = 0

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
            self.calls += 1
            payload = (variables or {}).get("input") or {}
            self.created.append(payload)
            ident = f"RA-800{self.calls}"
            return {
                "data": {
                    "issueCreate": {
                        "success": True,
                        "issue": {
                            "id": f"issue-{self.calls}",
                            "identifier": ident,
                            "title": payload.get("title") or title_from_goal("File this as a Linear ticket now"),
                            "url": f"https://linear.app/unite-group/issue/{ident}",
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
    assert out["identifier"] == "RA-8001"
    assert out["url"].endswith("RA-8001")
    assert out["state"] == "Backlog"
    assert _AUTONOMY_LABEL not in out["labels"]
    assert _SOURCE_LABEL in out["labels"]
    assert fake.created
    first = fake.created[0]
    assert first["projectId"] == PI_DEV_OPS_LINEAR_PROJECT
    assert first["teamId"] == PI_DEV_OPS_TEAM
    assert first["stateId"] == "state-backlog"
    assert first["stateId"] != "state-ready"
    assert first["labelIds"] == ["label-source"]
    assert _AUTONOMY_LABEL not in first["description"]
    assert _READY_STATE not in first["description"]


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
    def fake_file(
        repo: str,
        drafts: list[dict[str, Any]],
        *,
        approved: bool,
        parent_goal: str = "",
        gql: Any = None,
    ) -> dict[str, Any]:
        assert approved is True
        assert len(drafts) == 1
        assert "Linear" in parent_goal
        return {
            "status": "created",
            "count": 1,
            "tickets": [
                {
                    "identifier": "RA-8001",
                    "url": "https://linear.app/unite-group/issue/RA-8001",
                    "title": drafts[0]["title"],
                    "state": "Backlog",
                    "labels": [_SOURCE_LABEL],
                }
            ],
        }

    monkeypatch.setattr(goal_ticket_route, "file_drafts", fake_file)
    resp = client.post(
        "/api/goal-ticket",
        json={
            "goal": "File this as a Linear ticket now",
            "repo": "CleanExpo/Pi-Dev-Ops",
            "acceptance": "Ticket RA-8001 exists in Linear Backlog.",
            "approved": True,
            "tickets": [
                {
                    "title": "File this as a Linear ticket now",
                    "goal": "File this as a Linear ticket now",
                    "acceptance": "Ticket RA-8001 exists in Linear Backlog.",
                    "rationale": "Single hop",
                }
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tickets"][0]["identifier"] == "RA-8001"
    assert body["tickets"][0]["url"].endswith("RA-8001")
    assert body["tickets"][0]["state"] == "Backlog"
    assert _AUTONOMY_LABEL not in body["tickets"][0]["labels"]


def test_route_rejects_empty_body(client: TestClient) -> None:
    resp = client.post("/api/goal-ticket", json={"goal": "", "repo": "", "acceptance": ""})
    assert resp.status_code == 422


def test_file_drafts_refuses_without_approval() -> None:
    fake = _FakeLinear()
    out = file_drafts(
        "CleanExpo/Pi-Dev-Ops",
        [
            {
                "title": "Do not file this ticket yet",
                "goal": "This draft must not hit Linear",
                "acceptance": "No Linear issue exists for this draft.",
            }
        ],
        approved=False,
        gql=fake,
    )
    assert out["error"] == "not_approved"
    assert fake.created == []


def test_file_drafts_creates_each_approved_ticket() -> None:
    fake = _FakeLinear()
    out = file_drafts(
        "CleanExpo/Pi-Dev-Ops",
        [
            {
                "title": "Add the form",
                "goal": "The goal form exists on Control",
                "acceptance": "A stranger can file a ticket from /control/goal.",
                "rationale": "UI hop",
            },
            {
                "title": "Add the API",
                "goal": "POST /api/goal-ticket files Backlog issues",
                "acceptance": "A test proves approval is required before write.",
                "rationale": "API hop",
            },
        ],
        approved=True,
        parent_goal="Ship Goal to Linear with approval",
        gql=fake,
    )
    assert out["status"] == "created"
    assert out["count"] == 2
    assert [t["identifier"] for t in out["tickets"]] == ["RA-8001", "RA-8002"]
    assert len(fake.created) == 2
    assert fake.created[0]["title"] == "Add the form"
    assert "Ship Goal to Linear with approval" in fake.created[0]["description"]
    assert _AUTONOMY_LABEL not in fake.created[0]["description"]


def test_drafts_from_payload_splits_valid_tickets() -> None:
    drafts = drafts_from_payload(
        {
            "tickets": [
                {
                    "title": "Ticket A",
                    "goal": "Surface A exists in the dashboard",
                    "acceptance": "A stranger can open surface A.",
                    "rationale": "UI",
                },
                {
                    "title": "Ticket B",
                    "goal": "API B returns the new payload",
                    "acceptance": "A test covers the new payload.",
                    "rationale": "API",
                },
            ]
        },
        "parent goal text here",
        "parent acceptance text here",
    )
    assert len(drafts) == 2
    assert drafts[0]["title"] == "Ticket A"


def test_drafts_from_payload_falls_back_when_empty() -> None:
    drafts = drafts_from_payload({}, "parent goal text here", "parent acceptance lives here")
    assert drafts == fallback_drafts("parent goal text here", "parent acceptance lives here")


@pytest.mark.asyncio
async def test_analyze_goal_does_not_write_linear() -> None:
    async def fake_complete(**kwargs: Any) -> tuple[str, float]:
        return (
            '{"summary":"Two hops.","product":"Operator files after review.",'
            '"engineering":"Analyze then approve.","split_reason":"UI vs API",'
            '"tickets":['
            '{"title":"UI review","goal":"Review screen shows proposed tickets",'
            '"acceptance":"Approve is required before Linear write.","rationale":"UX"},'
            '{"title":"API file","goal":"Approved drafts become Backlog issues",'
            '"acceptance":"A test proves not_approved refuses write.","rationale":"API"}'
            "]}",
            0.01,
        )

    out = await analyze_goal(
        "Analyze then file Linear tickets after approval",
        "CleanExpo/Pi-Dev-Ops",
        "Drafts appear first; Linear only after approve.",
        complete_fn=fake_complete,
    )
    assert out["status"] == "proposed"
    assert out["filed"] is False
    assert out["fallback"] is False
    assert len(out["tickets"]) == 2
    assert "issueCreate" not in str(out)


@pytest.mark.asyncio
async def test_analyze_goal_falls_back_when_model_fails() -> None:
    async def boom(**kwargs: Any) -> tuple[str, float]:
        raise RuntimeError("no model")

    out = await analyze_goal(
        "Analyze then file Linear tickets after approval",
        "CleanExpo/Pi-Dev-Ops",
        "Drafts appear first; Linear only after approve.",
        complete_fn=boom,
    )
    assert out["filed"] is False
    assert out["fallback"] is True
    assert len(out["tickets"]) == 1
    assert out["tickets"][0]["goal"].startswith("Analyze then file")


def test_route_rejects_unapproved_file(client: TestClient) -> None:
    resp = client.post(
        "/api/goal-ticket",
        json={
            "goal": "File this as a Linear ticket now",
            "repo": "CleanExpo/Pi-Dev-Ops",
            "acceptance": "Ticket should not exist yet in Linear.",
            "approved": False,
            "tickets": [
                {
                    "title": "Do not file",
                    "goal": "This must stay a draft only",
                    "acceptance": "No Linear issue is created.",
                }
            ],
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "not_approved"


def test_analyze_route_returns_drafts_not_identifiers(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_analyze(goal: str, repo: str, acceptance: str) -> dict[str, Any]:
        return {
            "status": "proposed",
            "filed": False,
            "fallback": False,
            "summary": "One ticket.",
            "product": "Operator reviews first.",
            "engineering": "No Linear write.",
            "split_reason": "atomic",
            "tickets": [
                {
                    "title": "File after approval",
                    "goal": goal,
                    "acceptance": acceptance,
                    "rationale": "single",
                }
            ],
        }

    monkeypatch.setattr(goal_ticket_route, "analyze_goal", fake_analyze)
    resp = client.post(
        "/api/goal-ticket/analyze",
        json={
            "goal": "File this as a Linear ticket now",
            "repo": "CleanExpo/Pi-Dev-Ops",
            "acceptance": "Drafts exist; Linear does not yet.",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["filed"] is False
    assert "identifier" not in body
    assert body["tickets"][0]["title"] == "File after approval"
