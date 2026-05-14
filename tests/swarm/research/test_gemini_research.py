"""Tests for swarm/research/gemini_research.py — RA-1986.

Validates the public API contract:
  * Citation roundtrips JSON
  * URL + model selection
  * depth="quick" forces flash model
  * depth="deep" bumps max_tokens
  * grounding chunks parse into Citation list
  * citations_required retry behaviour (both branches)
  * 429 retries with backoff
  * 401 raises AuthError immediately (no retry)
  * Network timeout raises TimeoutError

All HTTP calls are mocked — no real Gemini traffic at test time.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from swarm.research import gemini_research as gr
from swarm.research.gemini_research import (
    AuthError,
    Citation,
    EmptyResponseError,
    GroundingFailedError,
    RateLimitError,
    TimeoutError as GeminiTimeoutError,
    grounded_research,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.delenv("MARGOT_RESEARCH_MODEL", raising=False)
    yield


@pytest.fixture(autouse=True)
def _zero_backoff(monkeypatch):
    """Stub asyncio.sleep so retry tests don't actually wait."""
    async def _no_sleep(_s):
        return None
    monkeypatch.setattr(gr.asyncio, "sleep", _no_sleep)
    yield


def _fake_response(
    *,
    text: str = "Synthesised answer about IICRC S500.",
    chunks: list[dict[str, Any]] | None = None,
    supports: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a Gemini-shaped response dict."""
    candidate: dict[str, Any] = {
        "content": {"parts": [{"text": text}]},
    }
    if chunks is not None or supports is not None:
        candidate["groundingMetadata"] = {
            "groundingChunks": chunks or [],
            "groundingSupports": supports or [],
        }
    return {"candidates": [candidate]}


def _httpx_response(status: int, body: Any) -> httpx.Response:
    """Build a real httpx.Response so resp.json() / resp.text work as in prod."""
    if isinstance(body, (dict, list)):
        content = json.dumps(body).encode("utf-8")
        headers = {"content-type": "application/json"}
    else:
        content = str(body).encode("utf-8")
        headers = {"content-type": "text/plain"}
    return httpx.Response(
        status_code=status,
        content=content,
        headers=headers,
        request=httpx.Request("POST", "https://example.invalid/x"),
    )


class _MockAsyncClient:
    """Stand-in for httpx.AsyncClient as used inside _post_generate_content.

    Each test installs a list of scripted (status, body) responses; the
    mock pops them in order, records the request URL + body, and raises
    if the script is exhausted.
    """

    def __init__(self, script: list[tuple[int, Any]]):
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False

    async def post(self, url, *, headers=None, json=None):  # noqa: A002
        if not self.script:
            raise AssertionError("MockAsyncClient ran out of scripted responses")
        status, body = self.script.pop(0)
        self.calls.append({"url": url, "headers": headers, "body": json})
        if isinstance(body, Exception):
            raise body
        return _httpx_response(status, body)


def _install_mock_client(monkeypatch, script: list[tuple[int, Any]]) -> _MockAsyncClient:
    """Patch httpx.AsyncClient to return our mock for the duration of one test."""
    mock = _MockAsyncClient(script)
    monkeypatch.setattr(gr.httpx, "AsyncClient", lambda *a, **kw: mock)
    return mock


# ── Tests ────────────────────────────────────────────────────────────────────


# 1. Citation dataclass JSON roundtrip
def test_citation_roundtrips_through_json():
    c = Citation(
        url="https://iicrc.org/s500",
        title="IICRC S500 Standard",
        snippet="The S500 sets minimum requirements for water damage restoration.",
    )
    payload = json.dumps(asdict(c))
    restored = Citation(**json.loads(payload))
    assert restored == c
    assert restored.url == "https://iicrc.org/s500"


# 2. URL + model selection — env default is gemini-2.5-pro
async def test_calls_correct_url_with_default_model(monkeypatch):
    body = _fake_response(
        chunks=[{"web": {"uri": "https://iicrc.org/s500", "title": "IICRC S500"}}],
    )
    mock = _install_mock_client(monkeypatch, [(200, body)])

    result = await grounded_research("test topic", citations_required=True)

    assert result.model == "gemini-2.5-pro"
    assert len(mock.calls) == 1
    url = mock.calls[0]["url"]
    assert "models/gemini-2.5-pro:generateContent" in url
    assert "key=test-key-not-real" in url
    # The request body should include the google_search tool
    sent = mock.calls[0]["body"]
    assert sent["tools"] == [{"google_search": {}}]
    assert sent["contents"][0]["role"] == "user"
    assert sent["contents"][0]["parts"][0]["text"] == "test topic"


# 3. depth="quick" forces flash regardless of env
async def test_depth_quick_uses_flash_model(monkeypatch):
    monkeypatch.setenv("MARGOT_RESEARCH_MODEL", "gemini-3-pro-future")
    body = _fake_response(
        chunks=[{"web": {"uri": "https://example.com/x", "title": "X"}}],
    )
    mock = _install_mock_client(monkeypatch, [(200, body)])

    result = await grounded_research("quick topic", depth="quick")

    assert result.model == "gemini-2.5-flash"
    assert "models/gemini-2.5-flash:generateContent" in mock.calls[0]["url"]


# 4. depth="deep" bumps max_tokens to 8192
async def test_depth_deep_bumps_max_tokens(monkeypatch):
    body = _fake_response(
        chunks=[{"web": {"uri": "https://example.com/y", "title": "Y"}}],
    )
    mock = _install_mock_client(monkeypatch, [(200, body)])

    await grounded_research("deep topic", depth="deep", max_tokens=4096)

    sent = mock.calls[0]["body"]
    assert sent["generationConfig"]["maxOutputTokens"] == 8192


# 5. 3 grounding chunks parse to 3 citations w/ snippets
async def test_grounding_chunks_parse_to_citations(monkeypatch):
    body = _fake_response(
        text="Three sources cited.",
        chunks=[
            {"web": {"uri": "https://iicrc.org/s500", "title": "IICRC S500"}},
            {"web": {"uri": "https://standards.org.au/as3500", "title": "AS/NZS 3500"}},
            {"web": {"uri": "https://masterbuilders.com.au/wd", "title": "MB Water Damage"}},
        ],
        supports=[
            {
                "segment": {"text": "IICRC S500 is the global benchmark."},
                "groundingChunkIndices": [0],
            },
            {
                "segment": {"text": "AS/NZS 3500 covers plumbing."},
                "groundingChunkIndices": [1],
            },
        ],
    )
    _install_mock_client(monkeypatch, [(200, body)])

    result = await grounded_research("water damage Australia")

    assert result.grounding_used is True
    assert len(result.citations) == 3
    assert result.citations[0].url == "https://iicrc.org/s500"
    assert result.citations[0].title == "IICRC S500"
    assert "global benchmark" in result.citations[0].snippet
    # Third chunk has no support → empty snippet, not crash
    assert result.citations[2].snippet == ""


# 6. citations_required=True + zero chunks → retries once, succeeds
async def test_citations_required_retries_once_and_succeeds(monkeypatch):
    first = _fake_response(text="No sources cited.")  # no groundingMetadata
    second = _fake_response(
        text="Now with [1] citations.",
        chunks=[{"web": {"uri": "https://iicrc.org/s500", "title": "IICRC"}}],
    )
    mock = _install_mock_client(monkeypatch, [(200, first), (200, second)])

    result = await grounded_research(
        "needs citation", citations_required=True,
    )

    assert len(mock.calls) == 2
    assert result.grounding_used is True
    assert len(result.citations) == 1
    # Second request includes the re-prompt instruction
    second_body = mock.calls[1]["body"]
    assert "explicit citation markers" in second_body["contents"][0]["parts"][0]["text"]


# 6b. citations_required=True + still zero on retry → GroundingFailedError
async def test_citations_required_retries_then_raises(monkeypatch):
    first = _fake_response(text="No sources cited.")
    second = _fake_response(text="Still no sources after re-prompt.")
    _install_mock_client(monkeypatch, [(200, first), (200, second)])

    with pytest.raises(GroundingFailedError) as exc_info:
        await grounded_research("needs citation", citations_required=True)

    err = exc_info.value
    assert err.partial is not None
    assert err.partial.grounding_used is False
    assert err.partial.citations == []


# 7. citations_required=False + zero chunks → returns empty citations
async def test_citations_optional_returns_empty_citations(monkeypatch):
    body = _fake_response(text="Some answer, no sources.")
    mock = _install_mock_client(monkeypatch, [(200, body)])

    result = await grounded_research(
        "no citations needed", citations_required=False,
    )

    assert len(mock.calls) == 1  # no retry
    assert result.grounding_used is False
    assert result.citations == []
    assert result.text == "Some answer, no sources."


# 8. HTTP 429 retries 3 times then raises RateLimitError
async def test_http_429_retries_three_times(monkeypatch):
    script = [
        (429, {"error": "rate-limited"}),
        (429, {"error": "rate-limited"}),
        (429, {"error": "rate-limited"}),
        (429, {"error": "rate-limited"}),  # 4th still 429 → raise
    ]
    mock = _install_mock_client(monkeypatch, script)

    with pytest.raises(RateLimitError):
        await grounded_research("rl topic", citations_required=False)

    # 1 initial + 3 retries = 4 calls
    assert len(mock.calls) == 4


# 9. HTTP 401 raises AuthError immediately (no retry)
async def test_http_401_raises_auth_error_no_retry(monkeypatch):
    mock = _install_mock_client(monkeypatch, [(401, {"error": "bad key"})])

    with pytest.raises(AuthError):
        await grounded_research("auth topic", citations_required=False)

    assert len(mock.calls) == 1  # no retry


# 10. Network timeout raises TimeoutError
async def test_network_timeout_raises_timeout_error(monkeypatch):
    timeout_exc = httpx.TimeoutException("connect timeout")
    _install_mock_client(monkeypatch, [(0, timeout_exc)])

    with pytest.raises(GeminiTimeoutError):
        await grounded_research("timeout topic", citations_required=False)


# Bonus: AuthError fires when GEMINI_API_KEY is missing entirely
async def test_missing_api_key_raises_auth_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(AuthError):
        await grounded_research("no key", citations_required=False)


# Bonus: empty 200 (no candidates, no text) → EmptyResponseError
async def test_empty_response_raises(monkeypatch):
    _install_mock_client(monkeypatch, [(200, {"candidates": []})])
    with pytest.raises(EmptyResponseError):
        await grounded_research("empty", citations_required=False)


# Bonus: explicit model override beats env
async def test_explicit_model_override_beats_env(monkeypatch):
    monkeypatch.setenv("MARGOT_RESEARCH_MODEL", "from-env")
    body = _fake_response(
        chunks=[{"web": {"uri": "https://x", "title": "X"}}],
    )
    mock = _install_mock_client(monkeypatch, [(200, body)])

    result = await grounded_research("topic", model="explicit-model")

    assert result.model == "explicit-model"
    assert "models/explicit-model:generateContent" in mock.calls[0]["url"]


# Bonus: env-driven model swap (proves Gemini 3.x landing is one env-var away)
async def test_env_model_swap(monkeypatch):
    monkeypatch.setenv("MARGOT_RESEARCH_MODEL", "gemini-3-pro-preview")
    body = _fake_response(
        chunks=[{"web": {"uri": "https://x", "title": "X"}}],
    )
    mock = _install_mock_client(monkeypatch, [(200, body)])

    result = await grounded_research("future topic")

    assert result.model == "gemini-3-pro-preview"
    assert "models/gemini-3-pro-preview:generateContent" in mock.calls[0]["url"]
