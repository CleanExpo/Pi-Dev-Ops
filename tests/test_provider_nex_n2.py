"""tests/test_provider_nex_n2.py — nex-agi/nex-n2-pro:free secondary model tests.

Covers:
  1. Model is registered and policy-allowed for research/suggestion roles.
  2. reasoning parameter is sent for nex-n2-pro calls.
  3. reasoning_details are captured and preserved across a simulated 2-turn
     multi-turn continuation.
  4. NEX_N2_RESEARCH_ENABLED=false → model not used (no HTTP call made).
  5. 429 rate-limit → graceful fallback (no exception, empty reasoning_details).

All tests use mock httpx — no real OpenRouter calls.
"""
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server import provider_nex_n2 as N2  # noqa: E402
from app.server import provider_router as PR  # noqa: E402


# ── Shared fake HTTP helpers ─────────────────────────────────────────────────


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int,
        body: dict | None = None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._body = body or {}
        self.text = text

    def json(self) -> dict:
        return self._body


class _FakeClient:
    """Captures the last request body so tests can inspect it."""

    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.last_json: dict | None = None

    def post(self, url: str, headers: dict | None = None, json: dict | None = None) -> _FakeResponse:
        self.last_json = json
        return self._response

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *a: Any) -> bool:
        return False


def _install_fake_httpx(
    monkeypatch: pytest.MonkeyPatch,
    response: _FakeResponse,
) -> _FakeClient:
    """Patch httpx.Client so all HTTP calls are intercepted."""
    client_instance = _FakeClient(response)
    fake_httpx = types.SimpleNamespace(Client=lambda timeout: client_instance)
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)
    return client_instance


def _success_body(
    content: str = "Research insight from nex-n2-pro.",
    reasoning: list | None = None,
) -> dict:
    """Build a well-formed OpenRouter chat-completions success response."""
    msg: dict = {"content": content}
    if reasoning is not None:
        msg["reasoning"] = reasoning
    return {
        "choices": [{"message": msg}],
        "usage": {"cost": 0.0},
    }


@pytest.fixture(autouse=True)
def _env_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset env vars to known defaults before each test."""
    monkeypatch.delenv("NEX_N2_RESEARCH_ENABLED", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


# ── 1. Model registration + policy ──────────────────────────────────────────


def test_model_id_is_registered():
    assert N2.NEX_N2_MODEL_ID == "nex-agi/nex-n2-pro:free"


def test_free_until_constant():
    """Expiry marker must exist and point to trial end date."""
    assert N2.NEX_N2_FREE_UNTIL == "2026-06-25"


def test_policy_allowed_for_research_roles():
    for role in ("research", "research.realtime", "suggestion"):
        assert N2.policy_allowed(role), f"Expected {role} to be policy-allowed"


def test_policy_allowed_for_secondary_board_and_brief():
    assert N2.policy_allowed("board")
    assert N2.policy_allowed("senior_brief")


def test_policy_not_allowed_for_primary_only_roles():
    """Generator/evaluator/orchestrator must NOT be allowed for nex-n2 secondary."""
    for role in ("generator", "evaluator", "orchestrator", "planner"):
        assert not N2.policy_allowed(role), (
            f"{role} should NOT be allowed for nex-n2 secondary"
        )


def test_research_role_is_in_provider_router_role_tier():
    """research + suggestion roles are registered in provider_router.ROLE_TIER."""
    assert "research" in PR.ROLE_TIER
    assert "suggestion" in PR.ROLE_TIER


def test_run_secondary_research_pass_is_exported():
    assert callable(PR.run_secondary_research_pass)


# ── 2. reasoning parameter is sent ───────────────────────────────────────────


def test_build_body_includes_reasoning_param():
    """_build_body must send the reasoning parameter for nex-n2-pro."""
    messages = [{"role": "user", "content": "Summarise the market."}]
    body = N2._build_body(messages, max_tokens=1024)
    assert body["model"] == N2.NEX_N2_MODEL_ID
    assert "reasoning" in body, "reasoning param must be present in request body"
    assert body["reasoning"].get("effort") in ("high", "medium", "low"), (
        "reasoning effort must be set"
    )


def test_call_sends_reasoning_param_in_http_body(monkeypatch: pytest.MonkeyPatch):
    """End-to-end: call() sends reasoning param to the HTTP endpoint."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    body = _success_body(
        content="Insight.",
        reasoning=[{"type": "thinking", "thinking": "Step 1: consider X"}],
    )
    client = _install_fake_httpx(monkeypatch, _FakeResponse(status_code=200, body=body))

    rc, text, cost, error, reasoning_details = asyncio.run(
        N2.call(prompt="Analyse this.", role="research")
    )

    assert rc == 0, f"Expected rc=0, got error={error}"
    assert client.last_json is not None, "HTTP body was not captured"
    assert "reasoning" in client.last_json, (
        "reasoning param must be present in the HTTP request body"
    )


# ── 3. reasoning_details captured and round-tripped ──────────────────────────


def test_extract_reasoning_details_from_response():
    """_extract_reasoning_details parses the reasoning list from the message."""
    steps = [
        {"type": "thinking", "thinking": "Step 1: identify key variables."},
        {"type": "thinking", "thinking": "Step 2: weigh trade-offs."},
    ]
    response = _success_body(content="Final answer.", reasoning=steps)
    result = N2._extract_reasoning_details(response)
    assert result == steps


def test_extract_reasoning_details_empty_when_absent():
    response = _success_body(content="Answer with no reasoning field.")
    # No `reasoning` key in message — should return empty list
    result = N2._extract_reasoning_details(response)
    assert result == []


def test_reasoning_details_round_trip_multi_turn(monkeypatch: pytest.MonkeyPatch):
    """Simulate a 2-turn conversation:
       Turn 1 → captures reasoning_details.
       Turn 2 → sends prior assistant message WITH reasoning preserved.

    Verifies that build_assistant_message_with_reasoning includes the
    reasoning field, and that the second call's body contains it.
    """
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    turn1_reasoning = [
        {"type": "thinking", "thinking": "First, consider the competitive moat."},
        {"type": "thinking", "thinking": "Then evaluate defensibility."},
    ]

    # --- Turn 1 ---
    turn1_response = _success_body(
        content="The primary moat is switching cost.",
        reasoning=turn1_reasoning,
    )
    client1 = _install_fake_httpx(monkeypatch, _FakeResponse(status_code=200, body=turn1_response))

    rc1, text1, _, err1, rd1 = asyncio.run(
        N2.call(prompt="What is the competitive moat?", role="research")
    )
    assert rc1 == 0, f"Turn 1 failed: {err1}"
    assert rd1 == turn1_reasoning, "Turn 1 reasoning_details not captured correctly"

    # --- Preserve reasoning in the history ---
    assistant_msg = N2.build_assistant_message_with_reasoning(text1, rd1)
    assert assistant_msg["role"] == "assistant"
    assert assistant_msg["reasoning"] == turn1_reasoning, (
        "build_assistant_message_with_reasoning must embed reasoning_details"
    )

    # --- Turn 2 ---
    turn2_response = _success_body(
        content="The secondary moat is brand loyalty.",
        reasoning=[{"type": "thinking", "thinking": "Brand recall is durable."}],
    )
    client2 = _install_fake_httpx(monkeypatch, _FakeResponse(status_code=200, body=turn2_response))

    history = [assistant_msg]
    rc2, text2, _, err2, rd2 = asyncio.run(
        N2.call(
            prompt="What about secondary moats?",
            role="research",
            history=history,
        )
    )
    assert rc2 == 0, f"Turn 2 failed: {err2}"

    # Verify the HTTP body for turn 2 contains the prior assistant message
    # with reasoning preserved
    body2 = client2.last_json
    assert body2 is not None
    messages_sent = body2.get("messages", [])
    # Should be: [prior assistant message, new user turn]
    assert len(messages_sent) >= 2, "History must be included in turn 2 body"

    # Find the assistant message in the sent body
    asst_messages = [m for m in messages_sent if m.get("role") == "assistant"]
    assert asst_messages, "Prior assistant message must be in turn 2 history"
    asst_msg_sent = asst_messages[0]
    assert "reasoning" in asst_msg_sent, (
        "reasoning_details must be preserved in the assistant turn sent to the model"
    )
    assert asst_msg_sent["reasoning"] == turn1_reasoning


def test_build_assistant_message_without_reasoning():
    """When reasoning_details is empty, the key is not included."""
    msg = N2.build_assistant_message_with_reasoning("Answer.", [])
    assert msg == {"role": "assistant", "content": "Answer."}
    assert "reasoning" not in msg


# ── 4. Flag-off → model not used ─────────────────────────────────────────────


def test_call_returns_disabled_when_flag_off(monkeypatch: pytest.MonkeyPatch):
    """NEX_N2_RESEARCH_ENABLED=false → call returns immediately, no HTTP."""
    monkeypatch.setenv("NEX_N2_RESEARCH_ENABLED", "false")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    # Patch httpx to fail loudly if called — it should NOT be called
    def _should_not_be_called(*a, **kw):
        raise AssertionError("HTTP was called despite NEX_N2_RESEARCH_ENABLED=false")

    fake_httpx = types.SimpleNamespace(Client=_should_not_be_called)
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    rc, text, cost, error, rd = asyncio.run(
        N2.call(prompt="Should not reach HTTP.", role="research")
    )
    assert rc == 1
    assert error == "nex_n2_disabled"
    assert text == ""
    assert rd == []


def test_research_pass_returns_fallback_when_flag_off(monkeypatch: pytest.MonkeyPatch):
    """research_pass returns fallback_text when disabled."""
    monkeypatch.setenv("NEX_N2_RESEARCH_ENABLED", "false")

    text, rd = asyncio.run(
        N2.research_pass(
            "Query", role="research", fallback_text="primary-result",
        )
    )
    assert text == "primary-result"
    assert rd == []


def test_is_enabled_false_variants(monkeypatch: pytest.MonkeyPatch):
    for val in ("false", "0", "no", "off"):
        monkeypatch.setenv("NEX_N2_RESEARCH_ENABLED", val)
        assert not N2.is_enabled(), f"is_enabled() should be False for {val!r}"


def test_is_enabled_true_by_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("NEX_N2_RESEARCH_ENABLED", raising=False)
    assert N2.is_enabled()


# ── 5. 429 → graceful fallback ───────────────────────────────────────────────


def test_call_rate_limit_429_returns_error_no_crash(monkeypatch: pytest.MonkeyPatch):
    """Free model 429 → rc=1, explicit error string, no exception raised."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    _install_fake_httpx(monkeypatch, _FakeResponse(status_code=429, text="Rate limited"))

    rc, text, cost, error, rd = asyncio.run(
        N2.call(prompt="Hi", role="research")
    )
    assert rc == 1
    assert error == "openrouter_http_429"
    assert text == ""
    assert rd == []


def test_research_pass_falls_back_on_429(monkeypatch: pytest.MonkeyPatch):
    """research_pass returns fallback_text on 429 without raising."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    _install_fake_httpx(monkeypatch, _FakeResponse(status_code=429, text="Rate limited"))

    text, rd = asyncio.run(
        N2.research_pass(
            "Query", role="research", fallback_text="primary-fallback",
        )
    )
    assert text == "primary-fallback"
    assert rd == []


def test_research_pass_falls_back_on_5xx(monkeypatch: pytest.MonkeyPatch):
    """research_pass returns fallback_text on 500 without raising."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    _install_fake_httpx(monkeypatch, _FakeResponse(status_code=500, text="Internal Error"))

    text, rd = asyncio.run(
        N2.research_pass(
            "Query", role="research", fallback_text="primary-fallback",
        )
    )
    assert text == "primary-fallback"
    assert rd == []


# ── router integration: run_secondary_research_pass ──────────────────────────


def test_router_secondary_pass_returns_fallback_when_disabled(monkeypatch: pytest.MonkeyPatch):
    """run_secondary_research_pass in provider_router respects the flag."""
    monkeypatch.setenv("NEX_N2_RESEARCH_ENABLED", "false")
    text, rd = asyncio.run(
        PR.run_secondary_research_pass(
            "Research this.",
            role="research",
            fallback_text="primary-only",
        )
    )
    assert text == "primary-only"
    assert rd == []


def test_router_secondary_pass_happy_path(monkeypatch: pytest.MonkeyPatch):
    """run_secondary_research_pass routes through nex-n2-pro when enabled."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.delenv("NEX_N2_RESEARCH_ENABLED", raising=False)

    steps = [{"type": "thinking", "thinking": "Reasoning step."}]
    body = _success_body(content="Secondary insight.", reasoning=steps)
    _install_fake_httpx(monkeypatch, _FakeResponse(status_code=200, body=body))

    text, rd = asyncio.run(
        PR.run_secondary_research_pass(
            "What should we do next?",
            role="research",
        )
    )
    assert text == "Secondary insight."
    assert rd == steps
