"""Regression coverage for the plan-to-generator admission boundary."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.server import session_phases
from app.server.session_model import BuildSession


def _valid_plan(confidence: float = 0.9) -> str:
    return json.dumps(
        {
            "confidence": confidence,
            "risk_notes": "",
            "units": [
                {"id": 1, "title": "Prepare", "files": ["app/a.py"], "is_behavioral": False},
                {"id": 2, "title": "Build", "files": ["app/b.py"]},
                {"id": 3, "title": "Verify", "files": ["tests/test_b.py"]},
            ],
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sdk_result", "sdk_error", "expected_reason"),
    [
        ((1, "", 0.0), None, "exit status 1"),
        ((0, "", 0.0), None, "empty output"),
        ((0, "not-json", 0.0), None, "not valid JSON"),
        ((0, _valid_plan(0.69), 0.0), None, "below the required 70% floor"),
        (None, asyncio.TimeoutError(), "timed out"),
        (None, RuntimeError("provider disconnected"), "planner error"),
    ],
)
async def test_plan_failures_block_without_advancing_checkpoint(
    tmp_path, sdk_result, sdk_error, expected_reason
):
    session = BuildSession(repo_url="https://example.test/repo", workspace=str(tmp_path))
    session.last_completed_phase = "sandbox"
    sdk = AsyncMock(return_value=sdk_result)
    if sdk_error:
        sdk.side_effect = sdk_error

    with patch.object(session_phases, "_run_claude_via_sdk", new=sdk), \
         patch.object(session_phases, "em"), \
         patch.object(session_phases.persistence, "save_session") as save_session:
        accepted = await session_phases._phase_plan(session, "Implement the feature", "")

    assert accepted is False
    assert session.status == "blocked"
    assert expected_reason in (session.error or "")
    assert session.last_completed_phase == "sandbox"
    assert session.plan == ""
    save_session.assert_called()


@pytest.mark.asyncio
async def test_valid_plan_is_persisted_before_advancing_checkpoint(tmp_path):
    session = BuildSession(repo_url="https://example.test/repo", workspace=str(tmp_path))
    sdk = AsyncMock(return_value=(0, _valid_plan(), 0.0))

    with patch.object(session_phases, "_run_claude_via_sdk", new=sdk), \
         patch.object(session_phases, "em"), \
         patch.object(session_phases.persistence, "save_session") as save_session:
        accepted = await session_phases._phase_plan(session, "Implement the feature", "")

    assert accepted is True
    assert session.last_completed_phase == "plan"
    assert session.status == "created"
    assert "# Implementation Plan" in session.plan
    assert (tmp_path / ".pi-ceo" / session.id / "PLAN.md").is_file()
    save_session.assert_called()


@pytest.mark.asyncio
async def test_run_build_never_starts_generator_when_planner_blocks(tmp_path):
    session = BuildSession(
        repo_url="https://example.test/repo",
        workspace=str(tmp_path),
        complexity_tier="basic",
        base_sha="a" * 40,  # The mocked successful clone has a recorded base revision.
    )
    plan = AsyncMock(return_value=False)
    generate = AsyncMock(return_value=True)
    sync_linear = MagicMock()

    with patch.object(session_phases, "em"), \
         patch.object(session_phases, "_TAO_AVAILABLE", False), \
         patch.object(session_phases, "_notify_linear_session_started"), \
         patch.object(session_phases, "_phase_clone", new=AsyncMock(return_value=True)), \
         patch.object(session_phases, "_phase_analyze"), \
         patch.object(session_phases, "_phase_claude_check", new=AsyncMock(return_value=True)), \
         patch.object(session_phases, "_phase_sandbox", new=AsyncMock(return_value=True)), \
         patch.object(session_phases, "classify_intent", return_value="build"), \
         patch.object(session_phases, "retrieve_similar_episodes", new=AsyncMock(return_value=[])), \
         patch.object(session_phases, "build_structured_brief", return_value="structured spec"), \
         patch.object(session_phases, "_write_task_memory", new=AsyncMock()), \
         patch.object(session_phases, "_phase_plan", new=plan), \
         patch.object(session_phases, "_phase_generate", new=generate), \
         patch.object(session_phases, "_sync_linear_on_completion", new=sync_linear):
        await session_phases.run_build(session, brief="Implement the feature")

    plan.assert_awaited_once()
    generate.assert_not_awaited()
    sync_linear.assert_called_once_with(session)


@pytest.mark.asyncio
async def test_run_build_forwards_smoke_intent_to_planner(tmp_path):
    session = BuildSession(
        repo_url="https://example.test/repo",
        workspace=str(tmp_path),
        complexity_tier="basic",
        base_sha="a" * 40,
    )
    plan = AsyncMock(return_value=False)

    with patch.object(session_phases, "em"), \
         patch.object(session_phases, "_TAO_AVAILABLE", False), \
         patch.object(session_phases, "_notify_linear_session_started"), \
         patch.object(session_phases, "_phase_clone", new=AsyncMock(return_value=True)), \
         patch.object(session_phases, "_phase_analyze"), \
         patch.object(session_phases, "_phase_claude_check", new=AsyncMock(return_value=True)), \
         patch.object(session_phases, "_phase_sandbox", new=AsyncMock(return_value=True)), \
         patch.object(session_phases, "retrieve_similar_episodes", new=AsyncMock(return_value=[])), \
         patch.object(session_phases, "build_structured_brief", return_value="structured spec"), \
         patch.object(session_phases, "_write_task_memory", new=AsyncMock()), \
         patch.object(session_phases, "_phase_plan", new=plan), \
         patch.object(session_phases, "_phase_generate", new=AsyncMock(return_value=True)), \
         patch.object(session_phases, "_sync_linear_on_completion"):
        await session_phases.run_build(session, brief="Add a comment", intent="smoke")

    assert plan.await_args.kwargs.get("intent") == "smoke"


@pytest.mark.asyncio
async def test_smoke_intent_admits_plan_at_observed_55_percent(tmp_path):
    """RA-7546 run 35528063288 — smoke canary must reach generate at 55%."""
    session = BuildSession(repo_url="https://example.test/repo", workspace=str(tmp_path))
    session.last_completed_phase = "sandbox"
    sdk = AsyncMock(return_value=(0, _valid_plan(0.55), 0.0))

    with patch.object(session_phases, "_run_claude_via_sdk", new=sdk), \
         patch.object(session_phases, "em"), \
         patch.object(session_phases.persistence, "save_session"):
        accepted = await session_phases._phase_plan(
            session, "Add a one-line comment", "", intent="smoke",
        )

    assert accepted is True
    assert session.last_completed_phase == "plan"
    assert session.status != "blocked"
    assert (tmp_path / ".pi-ceo" / session.id / "PLAN.md").is_file()


@pytest.mark.asyncio
async def test_product_intent_still_blocks_55_percent(tmp_path):
    session = BuildSession(repo_url="https://example.test/repo", workspace=str(tmp_path))
    session.last_completed_phase = "sandbox"
    sdk = AsyncMock(return_value=(0, _valid_plan(0.55), 0.0))

    with patch.object(session_phases, "_run_claude_via_sdk", new=sdk), \
         patch.object(session_phases, "em"), \
         patch.object(session_phases.persistence, "save_session"):
        accepted = await session_phases._phase_plan(
            session, "Implement the feature", "", intent="feature",
        )

    assert accepted is False
    assert session.status == "blocked"
    assert "70%" in (session.error or "")
    assert session.last_completed_phase == "sandbox"


@pytest.mark.asyncio
async def test_smoke_intent_still_requires_valid_units(tmp_path):
    session = BuildSession(repo_url="https://example.test/repo", workspace=str(tmp_path))
    session.last_completed_phase = "sandbox"
    skinny = json.dumps({"confidence": 0.55, "risk_notes": "", "units": []})
    sdk = AsyncMock(return_value=(0, skinny, 0.0))

    with patch.object(session_phases, "_run_claude_via_sdk", new=sdk), \
         patch.object(session_phases, "em"), \
         patch.object(session_phases.persistence, "save_session"):
        accepted = await session_phases._phase_plan(
            session, "Add a one-line comment", "", intent="smoke",
        )

    assert accepted is False
    assert session.status == "blocked"
    assert "units" in (session.error or "")
    assert session.last_completed_phase == "sandbox"
