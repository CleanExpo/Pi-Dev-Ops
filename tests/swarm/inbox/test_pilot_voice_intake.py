"""Tests for intake_router._maybe_handle_pilot_voice.

Per ADR 003: voice replies to Pilot suggestion cards are routed through
the voice pipeline. StubTranscriber is caught gracefully.
"""
from unittest.mock import patch, MagicMock
from swarm.inbox import intake_router


def test_voice_reply_to_pilot_card_routes_to_voice_pipeline(monkeypatch, tmp_path):
    monkeypatch.setenv("PILOT_BOT_TOKEN", "tk")
    monkeypatch.setenv("PILOT_TENANT_SLUG", "phill")
    update = {"message": {
        "voice": {"file_id": "FILE_ID_123", "duration": 5},
        "chat": {"id": 999},
        "reply_to_message": {"message_id": 7},
    }}
    mem_instance = MagicMock()
    mem_instance.client.table.return_value.select.return_value.eq.return_value \
        .eq.return_value.limit.return_value.execute.return_value.data = [{"suggestion_id": 42}]
    with patch("swarm.pilot.memory.Memory", return_value=mem_instance), \
         patch("swarm.pilot.voice.download_voice_file") as dl, \
         patch("swarm.pilot.voice.route_voice_reply") as route:
        dl.return_value = MagicMock(read_bytes=lambda: b"OPUS")
        assert intake_router._maybe_handle_pilot_voice(update) is True
    route.assert_called_once()
    args = route.call_args.kwargs
    assert args["suggestion_id"] == 42
    assert args["tenant_slug"] == "phill"


def test_non_voice_update_returns_false():
    assert intake_router._maybe_handle_pilot_voice({"message": {"text": "hi"}}) is False


def test_voice_without_reply_to_returns_false():
    upd = {"message": {"voice": {"file_id": "x"}, "chat": {"id": 1}}}
    assert intake_router._maybe_handle_pilot_voice(upd) is False
