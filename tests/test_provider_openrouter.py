"""tests/test_provider_openrouter.py — OpenRouter wrapper smoke."""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_transport_parsing_from_policy(monkeypatch):
    """These mock-only tests cover parsing/failover; policy has its own denied-path suite."""
    from app.server import provider_policy
    monkeypatch.setattr(provider_policy, "require_transport", lambda *args, **kwargs: {})

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


def test_truncated_content_is_returned_but_reported(caplog):
    """A truncated read must not look like a complete one.

    The content is still the model's own output — long-form roles hit
    max_tokens routinely and the partial text is the useful result — so it is
    returned rather than discarded. But it is logged, so an incomplete answer
    is visible instead of silently passing as whole.
    """
    response = {
        "choices": [{
            "finish_reason": "length",
            "message": {"content": "a partial answer that ran out of budget"},
        }],
    }
    with caplog.at_level(logging.WARNING, logger="app.server.provider_openrouter"):
        text = POR._extract_text(response)

    assert text == "a partial answer that ran out of budget"
    assert any("incomplete" in r.getMessage() for r in caplog.records)


def test_clean_content_is_not_reported_as_incomplete():
    """Positive control: without this, the test above proves nothing."""
    response = {
        "choices": [{"finish_reason": "stop", "message": {"content": "whole answer"}}],
    }
    assert POR._extract_text(response) == "whole answer"
