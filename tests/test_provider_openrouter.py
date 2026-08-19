"""tests/test_provider_openrouter.py — OpenRouter wrapper smoke."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server import provider_openrouter as POR  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


# ── No-API-key path ─────────────────────────────────────────────────────────


def test_call_returns_no_api_key_error_when_unset():
    rc, text, cost, error = asyncio.run(POR.call(
        prompt="hi", model_id="z-ai/glm-4.7-flash",
    ))
    assert rc == 1
    assert error == "openrouter_no_api_key"


# ── Header / body shape ─────────────────────────────────────────────────────


def test_build_headers_includes_bearer_when_key_set(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    headers = POR._build_headers()
    assert headers["Authorization"] == "Bearer sk-or-test"
    assert headers["Content-Type"] == "application/json"
    assert "X-Title" in headers
    assert "HTTP-Referer" in headers


def test_build_headers_empty_when_no_key():
    headers = POR._build_headers()
    assert headers == {}


def test_build_body_shape():
    body = POR._build_body("hello", "z-ai/glm-4.7-flash", max_tokens=2048)
    assert body["model"] == "z-ai/glm-4.7-flash"
    assert body["messages"][0] == {"role": "user", "content": "hello"}
    assert body["max_tokens"] == 2048


# ── Response extraction ─────────────────────────────────────────────────────


def test_extract_text_from_well_formed_response():
    response = {
        "choices": [{"message": {"content": "hello back"}}],
    }
    assert POR._extract_text(response) == "hello back"


def test_extract_text_handles_missing_choices():
    assert POR._extract_text({}) == ""
    assert POR._extract_text({"choices": []}) == ""


# ── Reasoning-model handling ────────────────────────────────────────────────
#
# Reasoning-capable cheap-tier models (GLM 4.7 Flash, Nemotron 3) return the
# answer in ``message.reasoning`` and leave ``content`` null. Measured against
# the live API 2026-08-19: glm-4.7-flash served by DeepInfra returned
# content=None with reasoning='{"intent":"ticket"}'. Reading only ``content``
# turned that valid response into openrouter_empty_response.


def test_build_body_disables_reasoning():
    """Left on, a reasoning model spends the whole max_tokens on its trace.

    Measured: glm-4.7-flash at max_tokens=120 burned 122 reasoning tokens and
    returned finish_reason='length' with no content at all.
    """
    body = POR._build_body("hello", "z-ai/glm-4.7-flash", max_tokens=2048)
    assert body["reasoning"] == {"enabled": False}


def test_extract_text_falls_back_to_reasoning_when_content_is_null():
    response = {
        "choices": [{"message": {"content": None, "reasoning": '{"intent":"ticket"}'}}],
    }
    assert POR._extract_text(response) == '{"intent":"ticket"}'


def test_extract_text_prefers_content_over_reasoning():
    """When both are present, content is the answer and reasoning is the trace."""
    response = {
        "choices": [{
            "message": {"content": "the answer", "reasoning": "step 1, step 2"},
        }],
    }
    assert POR._extract_text(response) == "the answer"


def test_extract_text_empty_when_neither_content_nor_reasoning():
    """Both empty must still be empty — the fallback must not invent text.

    This is the case that still has to reach the caller as
    openrouter_empty_response.
    """
    assert POR._extract_text({"choices": [{"message": {}}]}) == ""
    assert POR._extract_text(
        {"choices": [{"message": {"content": None, "reasoning": None}}]},
    ) == ""
    assert POR._extract_text(
        {"choices": [{"message": {"content": "", "reasoning": ""}}]},
    ) == ''


def test_extract_cost_usd_from_usage_block():
    response = {"usage": {"cost": 0.000123}}
    assert POR._extract_cost_usd(response) == 0.000123


def test_extract_cost_usd_falls_back_to_total_cost():
    response = {"usage": {"total_cost": 0.5}}
    assert POR._extract_cost_usd(response) == 0.5


def test_extract_cost_usd_zero_when_absent():
    assert POR._extract_cost_usd({}) == 0.0
    assert POR._extract_cost_usd({"usage": {}}) == 0.0


def test_extract_cost_usd_handles_garbage():
    response = {"usage": {"cost": "not-a-number"}}
    assert POR._extract_cost_usd(response) == 0.0


# ── End-to-end with mocked HTTP ─────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, *, status_code: int, body: dict | None = None,
                  text: str = ""):
        self.status_code = status_code
        self._body = body or {}
        self.text = text

    def json(self):
        return self._body


class _FakeClient:
    def __init__(self, response: _FakeResponse):
        self._response = response

    def post(self, url, headers=None, json=None):
        return self._response

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _install_fake_httpx(monkeypatch, response: _FakeResponse):
    import types as _types
    fake_httpx = _types.SimpleNamespace(Client=lambda timeout: _FakeClient(response))
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)


def test_call_happy_path(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    body = {
        "choices": [{"message": {"content": "Margot's reply"}}],
        "usage": {"cost": 0.0001},
    }
    _install_fake_httpx(monkeypatch, _FakeResponse(status_code=200, body=body))

    rc, text, cost, error = asyncio.run(POR.call(
        prompt="hi", model_id="z-ai/glm-4.7-flash",
    ))
    assert rc == 0
    assert text == "Margot's reply"
    assert cost == 0.0001
    assert error is None


def test_call_http_400_returns_error(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    _install_fake_httpx(
        monkeypatch,
        _FakeResponse(status_code=400, text="Invalid model"),
    )
    rc, text, cost, error = asyncio.run(POR.call(
        prompt="hi", model_id="bogus/model",
    ))
    assert rc == 1
    assert error and "openrouter_http_400" in error
    assert "Invalid model" in error


def test_call_http_500_returns_error(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    _install_fake_httpx(
        monkeypatch, _FakeResponse(status_code=500, text="overloaded"),
    )
    rc, text, cost, error = asyncio.run(POR.call(
        prompt="hi", model_id="z-ai/glm-4.7-flash",
    ))
    assert rc == 1
    assert "openrouter_http_500" in error


def test_call_empty_response_returns_error(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    _install_fake_httpx(
        monkeypatch,
        _FakeResponse(status_code=200, body={"choices": [{"message": {"content": ""}}]}),
    )
    rc, text, cost, error = asyncio.run(POR.call(
        prompt="hi", model_id="z-ai/glm-4.7-flash",
    ))
    assert rc == 1
    assert error == "openrouter_empty_response"
