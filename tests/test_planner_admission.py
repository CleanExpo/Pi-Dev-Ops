"""RA-7546 — planner is JSON-only; SDK failures must name the real error."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.server import planner_admission as admission
from app.server.brief import classify_brief_complexity, classify_intent
from scripts.smoke_test_pipeline import TEST_BRIEF


def test_smoke_brief_is_detailed_so_planner_budget_is_120s() -> None:
    """Quiet-tip session 49e62041 used this brief and hit the 120 s SDK cap."""
    assert classify_brief_complexity(TEST_BRIEF) == "detailed"
    assert admission.plan_timeouts("detailed") == (120, 130)
    assert admission.plan_timeouts("advanced") == (120, 130)
    assert admission.plan_timeouts("basic") == (60, 70)
    assert admission.plan_timeouts("") == (60, 70)


def test_planner_overrides_disable_tools_not_allowed_tools() -> None:
    """allowed_tools=[] is a no-op in the Agent SDK; tools=[] is the kill switch."""
    overrides = admission.planner_agent_option_overrides()
    assert overrides["tools"] == []
    assert "allowed_tools" not in overrides
    assert overrides["max_turns"] == 1
    assert overrides["setting_sources"] == []


def test_apply_planner_options_only_for_planner_phase() -> None:
    base = {"cwd": "/tmp/ws", "permission_mode": "bypassPermissions"}
    other = admission.apply_planner_agent_options(dict(base), "generator")
    assert other == base
    planned = admission.apply_planner_agent_options(dict(base), "planner")
    assert planned["tools"] == []
    assert planned["max_turns"] == 1


@pytest.mark.parametrize(
    ("phase", "thinking", "is_fable", "expected"),
    [
        ("planner", "adaptive", False, "disabled"),
        ("planner.plan", "enabled", False, "disabled"),
        ("generator", "adaptive", False, "adaptive"),
        ("planner", "adaptive", True, "adaptive"),
    ],
)
def test_planner_thinking_mode(
    phase: str, thinking: str, is_fable: bool, expected: str
) -> None:
    assert admission.planner_thinking_mode(phase, thinking, is_fable=is_fable) == expected


@pytest.mark.parametrize(
    ("rc", "text", "expected"),
    [
        (1, "timeout after 120s", "planner returned exit status 1 (timeout after 120s)"),
        (1, "", "planner returned exit status 1"),
        (0, "", "planner returned empty output"),
        (0, "   ", "planner returned empty output"),
    ],
)
def test_sdk_failure_detail_surfaces_swallowed_timeout(
    rc: int, text: str, expected: str
) -> None:
    assert admission.sdk_failure_detail(rc, text) == expected


@pytest.mark.asyncio
async def test_phase_plan_block_reason_includes_sdk_timeout_text(tmp_path) -> None:
    from unittest.mock import AsyncMock

    from app.server import session_phases
    from app.server.session_model import BuildSession

    session = BuildSession(repo_url="https://example.test/repo", workspace=str(tmp_path))
    session.last_completed_phase = "sandbox"
    sdk = AsyncMock(return_value=(1, "timeout after 120s", 0.0))
    with patch.object(session_phases, "_run_claude_via_sdk", new=sdk), \
         patch.object(session_phases, "em"), \
         patch.object(session_phases.persistence, "save_session"):
        accepted = await session_phases._phase_plan(session, "Implement the feature", "")

    assert accepted is False
    assert session.status == "blocked"
    assert "timeout after 120s" in (session.error or "")
    assert session.last_completed_phase == "sandbox"


def test_compose_agent_options_planner_is_json_only() -> None:
    planned = admission.compose_agent_options(
        workspace="/tmp/ws",
        model="sonnet",
        thinking_cfg=object(),
        effort=None,
        betas=[],
        gate_on=False,
        phase="planner",
    )
    assert planned["tools"] == []
    assert planned["max_turns"] == 1
    assert planned["setting_sources"] == []
    assert planned["permission_mode"] == "bypassPermissions"

    generated = admission.compose_agent_options(
        workspace="/tmp/ws",
        model="sonnet",
        thinking_cfg=object(),
        effort=None,
        betas=[],
        gate_on=False,
        phase="generator",
    )
    assert "tools" not in generated
    assert "max_turns" not in generated


@pytest.mark.asyncio
async def test_planner_sdk_call_sets_no_tools_and_disabled_thinking(monkeypatch) -> None:
    from app.server import provider_policy, session_sdk
    import sys
    monkeypatch.setattr(provider_policy, "require_transport", lambda *a, **kw: {})
    monkeypatch.setattr(session_sdk, "_execution_options", lambda _: {"cli_path": sys.executable, "env": {}})
    monkeypatch.setattr(session_sdk, "_write_sdk_metric", lambda **kw: None)
    from app.server.session_sdk import _run_claude_via_sdk
    from claude_agent_sdk import AssistantMessage, TextBlock, ResultMessage

    captured: dict[str, object] = {}

    async def mock_query(prompt=None, options=None):  # noqa: ARG001
        captured["options"] = options
        yield AssistantMessage(content=[TextBlock(text='{"ok":true}')], model="sonnet")
        yield MagicMock(spec=ResultMessage)

    with patch("claude_agent_sdk.query", mock_query):
        rc, text, _cost = await _run_claude_via_sdk(
            "emit json", "sonnet", "/tmp/ws", phase="planner",
        )

    assert rc == 0
    assert '{"ok":true}' in text
    options = captured["options"]
    assert getattr(options, "max_turns", None) == 1
    if hasattr(options, "tools"):
        assert options.tools == []
    thinking = getattr(options, "thinking", None)
    thinking_type = (
        thinking.get("type") if isinstance(thinking, dict)
        else getattr(thinking, "type", None)
    )
    assert thinking_type == "disabled"


def test_classify_intent_never_returns_smoke() -> None:
    """Smoke floor is API-only. Keyword classification cannot reach it."""
    assert classify_intent(TEST_BRIEF) != admission.SMOKE_INTENT
    assert classify_intent("Add a one-line comment to scripts/send_telegram.py") != "smoke"
    assert classify_intent("Fix the planner confidence floor") != "smoke"
    assert classify_intent("") != "smoke"


@pytest.mark.parametrize(
    ("intent", "expected"),
    [
        ("", admission.PRODUCT_PLAN_CONFIDENCE_FLOOR),
        ("feature", admission.PRODUCT_PLAN_CONFIDENCE_FLOOR),
        ("bug", admission.PRODUCT_PLAN_CONFIDENCE_FLOOR),
        ("SMOKE", admission.SMOKE_PLAN_CONFIDENCE_FLOOR),
        (" smoke ", admission.SMOKE_PLAN_CONFIDENCE_FLOOR),
    ],
)
def test_plan_confidence_floor_is_smoke_only(intent: str, expected: float) -> None:
    assert admission.plan_confidence_floor(intent) == expected


def test_product_floor_still_blocks_observed_smoke_score() -> None:
    """Run 35528063288 returned 55%. Product plans must still die there."""
    reason = admission.plan_below_confidence_floor(0.55, "feature")
    assert reason is not None
    assert "55%" in reason
    assert "70%" in reason
    assert admission.plan_below_confidence_floor(0.69, "") is not None
    assert admission.plan_below_confidence_floor(0.70, "feature") is None


def test_smoke_floor_admits_observed_55_percent() -> None:
    assert admission.plan_below_confidence_floor(0.55, "smoke") is None
    assert admission.plan_below_confidence_floor(0.0, "smoke") is None
    assert admission.smoke_admitted_below_product_floor(0.55, "smoke") is True
    assert admission.smoke_admitted_below_product_floor(0.55, "feature") is False
    assert admission.smoke_admitted_below_product_floor(0.90, "smoke") is False
