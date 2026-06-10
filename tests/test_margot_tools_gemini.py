from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import margot_tools  # noqa: E402


def test_default_margot_server_path_falls_back_to_bundled(monkeypatch):
    monkeypatch.delenv("MARGOT_SERVER_PATH", raising=False)
    monkeypatch.setattr(margot_tools.Path, "home", lambda: Path("/missing-home"))

    path = margot_tools._default_margot_server_path()

    assert path == REPO_ROOT / "vendor" / "margot-deep-research" / "server.py"


def test_unwrap_mcp_structured_content():
    out = margot_tools._unwrap_mcp_tool_result({
        "content": [{"type": "text", "text": '{"report":"text result"}'}],
        "structuredContent": {"report": "structured result", "store": "fileSearchStores/x"},
        "isError": False,
    })

    assert out == {"report": "structured result", "store": "fileSearchStores/x"}


def test_unwrap_mcp_text_json_content():
    out = margot_tools._unwrap_mcp_tool_result({
        "content": [{"type": "text", "text": '{"report":"text result"}'}],
        "isError": False,
    })

    assert out == {"report": "text result"}


def test_gemini_research_fallback_returns_summary(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_TEXT_MODEL", "models/gemini-test")
    monkeypatch.setattr(margot_tools, "MARGOT_SERVER_PATH", Path("/missing/margot/server.py"))

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({
                "candidates": [
                    {"content": {"parts": [{"text": "Summary: evidence checked."}]}}
                ]
            }).encode("utf-8")

    seen: dict[str, object] = {}

    def fake_urlopen(req, timeout):  # noqa: ARG001
        seen["url"] = req.full_url
        seen["key"] = req.headers.get("X-goog-api-key")
        seen["body"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(margot_tools.urllib.request, "urlopen", fake_urlopen)

    out = margot_tools.deep_research("Brain proof", use_corpus=True)

    assert out["status"] == "ok"
    assert out["transport"] == "gemini"
    assert out["model"] == "gemini-test"
    assert out["corpus_used"] is False
    assert "evidence checked" in out["summary"]
    assert seen["url"].endswith("/models/gemini-test:generateContent")
    assert seen["key"] == "test-key"
    assert "Brain proof" in seen["body"]["contents"][0]["parts"][0]["text"]


def test_gemini_research_fallback_reports_empty_response(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(margot_tools, "MARGOT_SERVER_PATH", Path("/missing/margot/server.py"))

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"candidates":[]}'

    monkeypatch.setattr(margot_tools.urllib.request, "urlopen", lambda *_a, **_k: FakeResponse())

    out = margot_tools.deep_research("Brain proof", use_corpus=False)

    assert out["error"] == "gemini_empty_response"


def test_deep_research_max_gemini_fallback_is_explicit(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(margot_tools, "MARGOT_SERVER_PATH", Path("/missing/margot/server.py"))

    out = margot_tools.deep_research_max("Brain proof", use_corpus=True)

    assert out["error"] == "gemini_async_requires_margot_server"
