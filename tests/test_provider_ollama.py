"""tests/test_provider_ollama.py — local Ollama wrapper smoke."""
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server import provider_ollama as POL  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_state(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    POL.clear_reachability_cache()


# ── Defaults / URL helpers ──────────────────────────────────────────────────


def test_default_base_url():
    assert POL._base_url() == "http://localhost:11434/v1"


def test_default_tags_url():
    assert POL._tags_url() == "http://localhost:11434/api/tags"


def test_base_url_env_override(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://10.0.0.5:11434/v1")
    assert POL._base_url() == "http://10.0.0.5:11434/v1"
    assert POL._tags_url() == "http://10.0.0.5:11434/api/tags"


def test_base_url_strips_trailing_slash(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1/")
    assert POL._base_url() == "http://localhost:11434/v1"


# ── Headers / body / response shape ─────────────────────────────────────────


def test_build_headers():
    headers = POL._build_headers()
    assert headers["Authorization"] == "Bearer ollama"
    assert headers["Content-Type"] == "application/json"


def test_build_body_shape():
    body = POL._build_body("hello", "gemma4:latest", max_tokens=2048)
    assert body["model"] == "gemma4:latest"
    assert body["messages"][0] == {"role": "user", "content": "hello"}
    assert body["max_tokens"] == 2048


def test_extract_text_from_well_formed_response():
    response = {"choices": [{"message": {"content": "hi from gemma4"}}]}
    assert POL._extract_text(response) == "hi from gemma4"


def test_extract_text_handles_missing_choices():
    assert POL._extract_text({}) == ""
    assert POL._extract_text({"choices": []}) == ""


# ── Reachability probe ─────────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code

    def json(self):
        return {}


class _FakeClient:
    def __init__(self, response=None, raise_on_get: Exception | None = None):
        self._response = response
        self._raise = raise_on_get

    def get(self, url):
        if self._raise:
            raise self._raise
        return self._response

    def post(self, url, headers=None, json=None):
        return self._response

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _install_fake_httpx(monkeypatch, *, response=None,
                         raise_exc: Exception | None = None):
    fake_httpx = types.SimpleNamespace(
        Client=lambda timeout: _FakeClient(
            response=response, raise_on_get=raise_exc,
        ),
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)


def test_is_reachable_true_on_200(monkeypatch):
    POL.clear_reachability_cache()
    _install_fake_httpx(monkeypatch, response=_FakeResponse(200))
    assert POL.is_reachable() is True


def test_is_reachable_false_on_500(monkeypatch):
    POL.clear_reachability_cache()
    _install_fake_httpx(monkeypatch, response=_FakeResponse(500))
    assert POL.is_reachable() is False


def test_is_reachable_false_on_connection_error(monkeypatch):
    POL.clear_reachability_cache()
    _install_fake_httpx(
        monkeypatch, raise_exc=ConnectionError("refused"),
    )
    assert POL.is_reachable() is False


def test_is_reachable_caches_result(monkeypatch):
    """Second call within TTL doesn't re-probe."""
    POL.clear_reachability_cache()
    call_count = [0]

    class _CountingClient:
        def get(self, url):
            call_count[0] += 1
            return _FakeResponse(200)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    fake_httpx = types.SimpleNamespace(
        Client=lambda timeout: _CountingClient(),
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    POL.is_reachable()
    POL.is_reachable()
    POL.is_reachable()
    assert call_count[0] == 1  # only one network call


def test_is_reachable_force_refresh_bypasses_cache(monkeypatch):
    POL.clear_reachability_cache()
    call_count = [0]

    class _CountingClient:
        def get(self, url):
            call_count[0] += 1
            return _FakeResponse(200)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    fake_httpx = types.SimpleNamespace(
        Client=lambda timeout: _CountingClient(),
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    POL.is_reachable()
    POL.is_reachable(force_refresh=True)
    assert call_count[0] == 2


# ── End-to-end call ─────────────────────────────────────────────────────────


class _FakeJsonResponse:
    def __init__(self, *, status_code: int, body: dict | None = None,
                  text: str = ""):
        self.status_code = status_code
        self._body = body or {}
        self.text = text

    def json(self):
        return self._body


def _install_fake_post(monkeypatch, response: _FakeJsonResponse):
    class _FakeClient:
        def post(self, url, headers=None, json=None):
            return response

        def get(self, url):
            return response

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    fake_httpx = types.SimpleNamespace(Client=lambda timeout: _FakeClient())
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)


def test_call_happy_path(monkeypatch):
    body = {"choices": [{"message": {"content": "Margot via gemma4"}}]}
    _install_fake_post(monkeypatch, _FakeJsonResponse(status_code=200, body=body))

    rc, text, cost, error = asyncio.run(POL.call(
        prompt="hi", model_id="gemma4:latest",
    ))
    assert rc == 0
    assert text == "Margot via gemma4"
    assert cost == 0.0  # Ollama is free
    assert error is None


def test_call_http_500_returns_error(monkeypatch):
    _install_fake_post(
        monkeypatch,
        _FakeJsonResponse(status_code=500, text="model load failed"),
    )
    rc, text, cost, error = asyncio.run(POL.call(
        prompt="hi", model_id="gemma4:latest",
    ))
    assert rc == 1
    assert "ollama_http_500" in error
    assert "model load failed" in error


def test_call_empty_response_returns_error(monkeypatch):
    _install_fake_post(
        monkeypatch,
        _FakeJsonResponse(
            status_code=200,
            body={"choices": [{"message": {"content": ""}}]},
        ),
    )
    rc, text, cost, error = asyncio.run(POL.call(
        prompt="hi", model_id="gemma4:latest",
    ))
    assert rc == 1
    assert error == "ollama_empty_response"


def test_call_connection_error_returns_error(monkeypatch):
    class _ExplodingClient:
        def post(self, url, headers=None, json=None):
            raise ConnectionError("ollama daemon down")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    fake_httpx = types.SimpleNamespace(
        Client=lambda timeout: _ExplodingClient(),
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    rc, text, cost, error = asyncio.run(POL.call(
        prompt="hi", model_id="gemma4:latest",
    ))
    assert rc == 1
    assert "ollama_call_raised" in error
    assert "daemon down" in error
