"""Tests for swarm.pilot.voice — Transcriber Protocol + download + route.

Per ADR 003: Discuss verb triggers a voice-reply branch. Phase 4 ships
StubTranscriber that raises NotImplementedError; transcription provider
deferred to v1.1 ADR 004.
"""
import pytest
from unittest.mock import patch, MagicMock
from swarm.pilot import voice


def test_protocol_defines_transcribe_method():
    assert hasattr(voice.Transcriber, "transcribe")


def test_download_voice_file_calls_getfile_then_downloads(monkeypatch, tmp_path):
    monkeypatch.setenv("PILOT_BOT_TOKEN", "tk")
    info = MagicMock(
        json=lambda: {"ok": True, "result": {"file_path": "voice/abc.oga"}},
        status_code=200,
        raise_for_status=lambda: None,
    )
    blob = MagicMock(content=b"OPUS_DATA", status_code=200, raise_for_status=lambda: None)
    with patch("swarm.pilot.voice.requests.get", side_effect=[info, blob]):
        out = voice.download_voice_file(file_id="FILE123", dest_dir=tmp_path)
    assert out.exists() and out.read_bytes() == b"OPUS_DATA"
    assert out.suffix == ".oga"


def test_stub_transcriber_raises_not_implemented():
    with pytest.raises(NotImplementedError, match="transcription provider"):
        voice.StubTranscriber().transcribe(b"audio")


def test_route_voice_reply_calls_memory_record():
    mem = MagicMock()
    voice.route_voice_reply(
        suggestion_id=42,
        transcript="hello",
        tenant_slug="phill",
        memory=mem,
    )
    mem.record_voice_reply.assert_called_once_with(
        suggestion_id=42,
        transcript="hello",
        tenant_slug="phill",
    )
