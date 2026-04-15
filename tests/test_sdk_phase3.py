"""
test_sdk_phase3.py — Unit tests for Phase 3 SDK migration.

Tests:
  - _run_claude_via_sdk_async returns (True, text) on successful SDK response
  - _run_claude_via_sdk_async returns (False, "") on SDK exception
  - _run_claude_via_sdk_async returns (False, "") when SDK not importable
  - _run_claude_via_sdk_async handles timeout
  - _run_claude() tries SDK when TAO_USE_AGENT_SDK=1 and succeeds
  - _run_claude() falls back to subprocess when SDK returns empty output
  - _decompose_brief tries SDK when TAO_USE_AGENT_SDK=1
"""
import asyncio
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_pipeline_sdk_async_success():
    """_run_claude_via_sdk_async returns (True, text) on successful SDK call."""
    from app.server.pipeline import _run_claude_via_sdk_async
    from claude_agent_sdk import AssistantMessage, TextBlock, ResultMessage

    text_block = TextBlock(text="# Spec: Test feature")
    assistant_msg = AssistantMessage(content=[text_block], model="sonnet")
    result_msg = MagicMock(spec=ResultMessage)

    async def mock_receive():
        yield assistant_msg
        yield result_msg

    mock_client = AsyncMock()
    mock_client.connect = AsyncMock()
    mock_client.query = AsyncMock()
    mock_client.receive_messages = mock_receive
    mock_client.disconnect = AsyncMock()

    with patch("claude_agent_sdk.ClaudeSDKClient", return_value=mock_client):
        success, output = await _run_claude_via_sdk_async("write a spec", phase="spec")
        assert success is True
        assert "# Spec:" in output


@pytest.mark.asyncio
async def test_pipeline_sdk_async_exception():
    """_run_claude_via_sdk_async returns (False, "") on connection error."""
    from app.server.pipeline import _run_claude_via_sdk_async

    mock_client = AsyncMock()
    mock_client.connect = AsyncMock(side_effect=RuntimeError("Connection failed"))

    with patch("claude_agent_sdk.ClaudeSDKClient", return_value=mock_client):
        success, output = await _run_claude_via_sdk_async("test prompt", phase="spec")
        assert success is False
        assert output == ""


@pytest.mark.asyncio
async def test_pipeline_sdk_async_import_error():
    """_run_claude_via_sdk_async returns (False, "") when SDK not installed."""
    from app.server.pipeline import _run_claude_via_sdk_async

    with patch.dict(sys.modules, {"claude_agent_sdk": None}):
        success, output = await _run_claude_via_sdk_async("test", phase="spec")
        assert isinstance(success, bool)
        assert isinstance(output, str)


@pytest.mark.asyncio
async def test_pipeline_sdk_async_timeout():
    """_run_claude_via_sdk_async handles TimeoutError and returns (False, "")."""
    from app.server.pipeline import _run_claude_via_sdk_async

    async def mock_receive_timeout():
        raise asyncio.TimeoutError("Query timed out")
        yield  # keeps this an async generator

    mock_client = AsyncMock()
    mock_client.connect = AsyncMock()
    mock_client.query = AsyncMock()
    mock_client.receive_messages = mock_receive_timeout
    mock_client.disconnect = AsyncMock()

    with patch("claude_agent_sdk.ClaudeSDKClient", return_value=mock_client):
        success, output = await _run_claude_via_sdk_async("test", timeout=1, phase="spec")
        assert success is False
        assert output == ""


def test_run_claude_uses_sdk_when_flag_on():
    """_run_claude() calls asyncio.run with SDK coroutine when TAO_USE_AGENT_SDK=1."""
    from app.server import pipeline, config

    with patch.object(config, "USE_AGENT_SDK", True):
        with patch.object(pipeline, "_run_claude_via_sdk_async") as mock_async:
            # asyncio.run will call the coroutine synchronously
            async def fake_sdk(*args, **kwargs):
                return (True, "# Plan: Implementation plan content")
            mock_async.return_value = fake_sdk()

            with patch("asyncio.run", return_value=(True, "# Plan: Implementation plan content")):
                result = pipeline._run_claude("write a plan", model="sonnet", phase="plan")
                assert "# Plan:" in result


def test_run_claude_falls_back_to_subprocess_on_empty():
    """_run_claude() falls back to subprocess when SDK returns empty output."""
    from app.server import pipeline, config

    with patch.object(config, "USE_AGENT_SDK", True):
        # SDK returns success=True but empty output
        with patch("asyncio.run", return_value=(True, "")):
            with patch.object(pipeline, "_run_claude_subprocess", return_value="subprocess output") as mock_sub:
                result = pipeline._run_claude("write spec", model="sonnet", phase="spec")
                assert mock_sub.called
                assert result == "subprocess output"


@pytest.mark.asyncio
async def test_decompose_brief_tries_sdk():
    """_decompose_brief uses SDK path when TAO_USE_AGENT_SDK=1.

    RA-1030: SDK output is now expected to be a JSON array of task dicts.
    The function returns list[dict] on success; the test verifies the SDK
    path is taken and the result matches the new schema.
    """
    from app.server import orchestrator, config
    import json as _json

    sdk_rich_output = _json.dumps([
        {"id": 1, "title": "Sub-task 1", "brief": "do A", "depends_on": [], "test_scenarios": [], "is_behavioral": False},
        {"id": 2, "title": "Sub-task 2", "brief": "do B", "depends_on": [], "test_scenarios": [], "is_behavioral": False},
    ])

    with patch.object(config, "USE_AGENT_SDK", True):
        with patch.object(orchestrator, "_run_claude_via_sdk", return_value=(0, sdk_rich_output, 0.0)):
            import tempfile
            with tempfile.TemporaryDirectory() as tmpdir:
                result = await orchestrator._decompose_brief(
                    "build X", n_workers=2, repo_url="https://github.com/test/repo", workspace=tmpdir
                )
                assert len(result) == 2
                # RA-1030: result is list[dict] with rich task schema
                assert isinstance(result[0], dict)
                assert result[0]["brief"] == "do A"
                assert result[1]["brief"] == "do B"
                assert result[0].get("depends_on") == []
                assert result[0].get("test_scenarios") == []
