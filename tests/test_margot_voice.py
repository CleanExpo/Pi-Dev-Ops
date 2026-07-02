"""tests/test_margot_voice.py — Margot ElevenLabs voice SSOT."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server import margot_voice as mv  # noqa: E402


def test_resolve_margot_voice_id_canonical(monkeypatch):
    monkeypatch.delenv("MARGOT_ELEVENLABS_VOICE_ID", raising=False)
    monkeypatch.delenv("MARGOT_VOICE_ID", raising=False)
    mv._voice_id_from_identity_json.cache_clear()
    assert mv.resolve_margot_voice_id() == "p43fx6U8afP2xoq1Ai9f"


def test_resolve_margot_voice_id_ignores_generic_elevenlabs_env(monkeypatch):
    """ELEVENLABS_VOICE_ID is for other agents — must not affect Margot."""
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "other-agent-voice-id")
    monkeypatch.delenv("MARGOT_ELEVENLABS_VOICE_ID", raising=False)
    monkeypatch.delenv("MARGOT_VOICE_ID", raising=False)
    mv._voice_id_from_identity_json.cache_clear()
    assert mv.resolve_margot_voice_id() == "p43fx6U8afP2xoq1Ai9f"
    assert mv.resolve_margot_voice_id() != "other-agent-voice-id"
    monkeypatch.setenv("MARGOT_ELEVENLABS_VOICE_ID", "override-voice")
    mv._voice_id_from_identity_json.cache_clear()
    assert mv.resolve_margot_voice_id() == "override-voice"


def test_margot_identity_json_has_elevenlabs_voice_id():
    path = REPO_ROOT / ".harness" / "margot" / "assets" / "margot_identity.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["elevenlabs"]["voice_id"] == "p43fx6U8afP2xoq1Ai9f"


def test_synthesise_voice_defaults_to_margot_voice_id(monkeypatch, tmp_path):
    from swarm import voice_compose as VC  # noqa: E402

    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.delenv("MARGOT_ELEVENLABS_VOICE_ID", raising=False)
    mv._voice_id_from_identity_json.cache_clear()

    captured: dict[str, str] = {}

    class _Resp:
        content = b"audio"
        def raise_for_status(self) -> None:
            return None

    class _Client:
        def __init__(self, **_kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def post(self, url: str, **_kwargs):
            captured["url"] = url
            return _Resp()

    import httpx  # noqa: PLC0415
    monkeypatch.setattr(httpx, "Client", _Client)

    out = VC.synthesise_voice("hello", out_path=tmp_path / "x.mp3")
    assert out is not None
    assert "p43fx6U8afP2xoq1Ai9f" in captured["url"]
