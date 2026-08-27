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
from app.server.goal_analyze import (
    analyze_goal,
    drafts_from_payload,
    fallback_drafts,
    render_analyze_prompt,
)
from app.server.goal_projects import create_project
from app.server.goal_ticket_format import format_draft_notes
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


def test_route_returns_ticket_url(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, goal_project: dict[str, str]
) -> None:
    def fake_file(
        repo: str,
        drafts: list[dict[str, Any]],
        *,
        approved: bool,
        parent_goal: str = "",
        gql: Any = None,
        project_title: str = "",
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
            "acceptance": "Ticket RA-8001 exists in Linear Backlog.",
            "project_id": goal_project["id"],
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
    resp = client.post("/api/goal-ticket", json={"goal": "", "acceptance": "", "project_id": ""})
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
                "context": "The Control goal form",
                "current_behaviour": "No form on Control.",
                "expected_behaviour": "The goal form exists on Control",
                "technical_requirements": "GoalTicketForm on /control/goal",
                "testing": "Click analyze, see drafts, nothing in Linear.",
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
    assert "## Context" in fake.created[0]["description"]
    assert "The Control goal form" in fake.created[0]["description"]
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
    assert drafts == fallback_drafts("parent goal text here", "parent acceptance lives here", "")


@pytest.mark.asyncio
async def test_analyze_goal_does_not_write_linear(goal_project: dict[str, str]) -> None:
    async def fake_complete(**kwargs: Any) -> tuple[str, float]:
        return (
            '{"summary":"Two hops.","split_reason":"UI vs API",'
            '"tickets":['
            '{"title":"UI review","expected_behaviour":"Review screen shows proposed tickets",'
            '"acceptance":"Approve is required before Linear write.","context":"Control Goal",'
            '"current_behaviour":"No drafts.","technical_requirements":"GoalDraftReview",'
            '"testing":"Analyze then approve.","rationale":"UX"},'
            '{"title":"API file","expected_behaviour":"Approved drafts become Backlog issues",'
            '"acceptance":"A test proves not_approved refuses write.","context":"API",'
            '"current_behaviour":"No write gate.","technical_requirements":"file_drafts",'
            '"testing":"POST without approved is 400.","rationale":"API"}'
            "]}",
            0.01,
        )

    out = await analyze_goal(
        "Analyze then file Linear tickets after approval",
        "Drafts appear first; Linear only after approve.",
        goal_project["id"],
        complete_fn=fake_complete,
    )
    assert out["status"] == "proposed"
    assert out["filed"] is False
    assert out["fallback"] is False
    assert out["code_inspected"] is False
    assert out["project_title"] == goal_project["title"]
    assert len(out["tickets"]) == 2
    assert out["tickets"][0]["context"] == "Control Goal"
    assert "issueCreate" not in str(out)
    assert out["summary"] == "Two hops."


@pytest.mark.asyncio
async def test_analyze_goal_maps_nested_goal_analysis(goal_project: dict[str, str]) -> None:
    async def fake_complete(**kwargs: Any) -> tuple[str, float]:
        assert "{{GOAL}}" not in kwargs["prompt"]
        assert "Maximum 6 parent tickets" in kwargs["prompt"]
        return (
            '{"goal_analysis":{"summary":"Inspected Control Goal.","overall_risk":"Low"},'
            '"split_reason":"One ticket.",'
            '"user_flow":{"diagram":"User\\n↓\\nApprove"},'
            '"tickets":[{"id":"T1","priority":"P0","title":"Gate Linear write",'
            '"expected_behaviour":"Analyze then approve before Linear.",'
            '"acceptance":["Given drafts exist When approve Then Linear is written"]}]}',
            0.01,
        )

    out = await analyze_goal(
        "Analyze then file Linear tickets after approval",
        "Drafts appear first; Linear only after approve.",
        goal_project["id"],
        complete_fn=fake_complete,
    )
    assert out["filed"] is False
    assert out["summary"] == "Inspected Control Goal."
    assert out["goal_analysis"]["overall_risk"] == "Low"
    assert out["user_flow"]["diagram"].startswith("User")
    assert out["tickets"][0]["ticket_id"] == "T1"
    assert out["tickets"][0]["priority"] == "P0"


@pytest.mark.asyncio
async def test_analyze_goal_falls_back_when_model_fails(goal_project: dict[str, str]) -> None:
    async def boom(**kwargs: Any) -> tuple[str, float]:
        raise RuntimeError("no model")

    out = await analyze_goal(
        "Analyze then file Linear tickets after approval",
        "Drafts appear first; Linear only after approve.",
        goal_project["id"],
        complete_fn=boom,
    )
    assert out["filed"] is False
    assert out["fallback"] is True
    assert out["code_inspected"] is False
    assert out["tickets"][0]["current_behaviour"].startswith("Unknown")
    assert len(out["tickets"]) == 1
    assert out["summary"]
    assert "failed" in out["summary"].lower()


def test_route_rejects_unapproved_file(client: TestClient, goal_project: dict[str, str]) -> None:
    resp = client.post(
        "/api/goal-ticket",
        json={
            "goal": "File this as a Linear ticket now",
            "acceptance": "Ticket should not exist yet in Linear.",
            "project_id": goal_project["id"],
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
    client: TestClient, monkeypatch: pytest.MonkeyPatch, goal_project: dict[str, str]
) -> None:
    async def fake_analyze(goal: str, acceptance: str, project_id: str) -> dict[str, Any]:
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
            "acceptance": "Drafts exist; Linear does not yet.",
            "project_id": goal_project["id"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["filed"] is False
    assert "identifier" not in body
    assert body["tickets"][0]["title"] == "File after approval"


def test_format_draft_notes_includes_implementation_sections() -> None:
    body = format_draft_notes(
        {
            "context": "Synthex looks feed",
            "acceptance": "ignored here",
            "testing": "Playwright save-look path",
        }
    )
    assert "## Context" in body
    assert "Synthex looks feed" in body
    assert "## Testing" in body
    assert "Ready for Pi-Dev" not in body


def test_render_analyze_prompt_uses_project_brief() -> None:
    text = render_analyze_prompt(
        "Save a look on the feed",
        "Saved look remains after refresh.",
        {
            "title": "Synthex saved looks",
            "description": "People save looks from the feed.",
            "audience": "Shoppers on Synthex.",
            "problem": "",
            "users": "",
            "outcomes": "",
            "constraints": "",
            "out_of_scope": "",
        },
    )
    assert "Save a look on the feed" in text
    assert "Synthex saved looks" in text
    assert "Shoppers on Synthex." in text
    assert "{{GOAL}}" not in text
    assert "{{PROJECT}}" not in text
    assert "Maximum 6 parent tickets" in text
    assert "goal_analysis" in text
    assert "sub_tasks" in text


def test_drafts_from_payload_flattens_nested_schema() -> None:
    drafts = drafts_from_payload(
        {
            "goal_analysis": {"summary": "One ticket is enough."},
            "tickets": [
                {
                    "id": "T1",
                    "priority": "P0",
                    "title": "Add save look",
                    "expected_behaviour": "Look A appears in Saved after save.",
                    "acceptance": [
                        "Given the user is logged in When they save Look A Then it appears in Saved"
                    ],
                    "technical_requirements": ["Reuse the existing save API"],
                    "testing": {"unit": ["parser"], "e2e": ["save then refresh"]},
                    "scope": {"included": ["save button"], "excluded": ["new feed"]},
                    "review": {"clarity": "High", "main_risk": "unknown API shape"},
                    "ui_ux": {"required": True, "details": ["Use existing button styles"]},
                }
            ],
        },
        "parent goal text here",
        "parent acceptance text here",
    )
    assert len(drafts) == 1
    assert drafts[0]["ticket_id"] == "T1"
    assert drafts[0]["priority"] == "P0"
    assert "Included:" in drafts[0]["scope"]
    assert "e2e:" in drafts[0]["testing"]
    assert "clarity: High" in drafts[0]["review"]
    assert "Required." in drafts[0]["ui_ux"]


def test_drafts_from_payload_uses_parent_acceptance_when_ticket_omits_it() -> None:
    drafts = drafts_from_payload(
        {
            "tickets": [
                {
                    "title": "Add project create on the dashboard",
                    "summary": "User can create a project from the dashboard.",
                    "technical_requirements": ["Reuse the existing dashboard shell"],
                }
            ]
        },
        "Let a user create projects and tasks",
        "A user can create a project, add a task, and see status persist after refresh.",
    )
    assert len(drafts) == 1
    assert drafts[0]["title"] == "Add project create on the dashboard"
    assert "persist after refresh" in drafts[0]["acceptance"]


def test_drafts_from_payload_skips_schema_placeholder_tickets() -> None:
    drafts = drafts_from_payload(
        {
            "tickets": [
                {
                    "title": "Human-written imperative title <= 80 characters",
                    "expected_behaviour": "",
                    "acceptance": ["Given ... When ... Then ..."],
                }
            ]
        },
        "Let a user create projects and tasks",
        "A user can create a project, add a task, and see status persist after refresh.",
    )
    assert drafts[0]["rationale"].startswith("Single draft")


@pytest.mark.asyncio
async def test_analyze_goal_uses_project_not_repo(goal_project: dict[str, str]) -> None:
    async def fake_complete(**kwargs: Any) -> tuple[str, float]:
        assert "Do not inspect" in kwargs["system"] or "project brief" in kwargs["prompt"]
        assert "github.com" not in kwargs["prompt"].lower()
        return (
            '{"goal_analysis":{"summary":"Split by create then persist."},'
            '"split_reason":"UI vs persist.",'
            '"tickets":[{"title":"Create project from dashboard",'
            '"expected_behaviour":"User can create a named project.",'
            '"acceptance":["Given a logged-in user When they create a project Then it appears after refresh"],'
            '"tasks":["Add the create form"],'
            '"sub_tasks":[{"title":"Add the title field","description":"Title is required and persists.",'
            '"scenarios":["Given empty title When submit Then show an error"],'
            '"details":["Trim whitespace before save"]}]}]}',
            0.01,
        )

    out = await analyze_goal(
        "Let a user create projects, add tasks, and track task status from their dashboard",
        "A user can create a project, add a task, change its status, refresh, and see it persist.",
        goal_project["id"],
        complete_fn=fake_complete,
    )
    assert out["fallback"] is False
    assert out["code_inspected"] is False
    assert out["project_title"] == goal_project["title"]
    assert out["tickets"][0]["title"] == "Create project from dashboard"
    assert "Add the title field" in out["tickets"][0]["sub_tasks"]
    assert out["tickets"][0]["sub_tasks_json"]


def test_file_drafts_creates_parent_and_sub_tasks() -> None:
    fake = _FakeLinear()
    out = file_drafts(
        "CleanExpo/Pi-Dev-Ops",
        [
            {
                "title": "Add project create",
                "goal": "User can create a named project from the dashboard",
                "acceptance": "A created project remains after refresh.",
                "sub_tasks_json": (
                    '[{"title":"Add the title field","description":"Required title persists after save.",'
                    '"scenarios":"Given empty title When submit Then show an error",'
                    '"details":"Trim whitespace","acceptance":"Empty title is rejected with an error."}]'
                ),
            }
        ],
        approved=True,
        parent_goal="Let a user create projects",
        project_title="Control Goal desk",
        gql=fake,
    )
    assert out["status"] == "created"
    assert out["count"] == 2
    assert fake.created[0]["title"] == "Add project create"
    assert fake.created[1]["title"] == "Add the title field"
    assert fake.created[1]["parentId"] == "issue-1"
    assert "## Project" in fake.created[0]["description"]
    assert "Control Goal desk" in fake.created[0]["description"]
