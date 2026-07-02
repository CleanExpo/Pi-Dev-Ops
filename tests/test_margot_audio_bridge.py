"""Tests for Margot API voice bridge — audio_base64 on turn responses."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.server.routes import margot as margot_route


def test_encode_voice_attachment_returns_base64(tmp_path):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"\x00fake-mp3-bytes")
    turn = SimpleNamespace(voice_audio_path=str(audio))
    b64, mime = margot_route._encode_voice_attachment(turn)
    assert b64 is not None
    assert mime == "audio/mpeg"


def test_encode_voice_attachment_missing_file():
    turn = SimpleNamespace(voice_audio_path="/no/such/file.mp3")
    b64, mime = margot_route._encode_voice_attachment(turn)
    assert b64 is None
    assert mime is None


def test_response_from_turn_includes_audio(tmp_path):
    audio = tmp_path / "v.mp3"
    audio.write_bytes(b"mp3")
    turn = SimpleNamespace(
        margot_text="hello",
        cost_usd=0.01,
        research_called=False,
        board_session_ids=[],
        turn_id="mt-abc",
        voice_audio_path=str(audio),
    )
    payload = margot_route._response_from_turn(turn)
    assert payload["reply"] == "hello"
    assert payload["audio_base64"] is not None
    assert payload["audio_mime_type"] == "audio/mpeg"
