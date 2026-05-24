"""Tests for dispatcher.py — Telegram send + message-link persistence.

Per ADR 003: persists chat_id+message_id into pilot_suggestion_messages
for editMessageReplyMarkup lookups by feedback handlers.
"""
from unittest.mock import MagicMock, patch
from swarm.pilot import dispatcher
from swarm.pilot.types import RawCandidate


def _c():
    return RawCandidate(
        fingerprint="fp", headline="h", pillar=["Tier-2 Infra"],
        effort="XS", source="github", confidence="HIGH",
        body={}, impact_score=80,
    )


def test_dispatcher_calls_record_message_with_link(monkeypatch):
    monkeypatch.setenv("PILOT_BOT_TOKEN", "tk")
    monkeypatch.setenv("PILOT_BOT_CHAT_ID", "999")
    monkeypatch.setenv("PILOT_TENANT_SLUG", "phill")
    mem = MagicMock()
    mem.record_suggestion.return_value = 42
    with patch("swarm.pilot.dispatcher.requests.post") as p:
        p.return_value.json.return_value = {"ok": True, "result": {"message_id": 7}}
        p.return_value.status_code = 200
        dispatcher.send({"text": "h", "reply_markup": {"inline_keyboard": []}}, _c(), mem)
    mem.record_message.assert_called_once_with(
        suggestion_id=42, chat_id=999, message_id=7, tenant_slug="phill",
    )


def test_dispatcher_raises_on_telegram_api_error(monkeypatch):
    monkeypatch.setenv("PILOT_BOT_TOKEN", "tk")
    monkeypatch.setenv("PILOT_BOT_CHAT_ID", "999")
    monkeypatch.setenv("PILOT_TENANT_SLUG", "phill")
    mem = MagicMock()
    with patch("swarm.pilot.dispatcher.requests.post") as p:
        p.return_value.json.return_value = {"ok": False, "description": "Bad Request"}
        p.return_value.status_code = 400
        p.return_value.raise_for_status.return_value = None
        import pytest
        with pytest.raises(RuntimeError, match="Telegram API error"):
            dispatcher.send({"text": "h", "reply_markup": {"inline_keyboard": []}}, _c(), mem)


def test_dispatcher_returns_suggestion_id(monkeypatch):
    monkeypatch.setenv("PILOT_BOT_TOKEN", "tk")
    monkeypatch.setenv("PILOT_BOT_CHAT_ID", "123")
    monkeypatch.setenv("PILOT_TENANT_SLUG", "phill")
    mem = MagicMock()
    mem.record_suggestion.return_value = 99
    with patch("swarm.pilot.dispatcher.requests.post") as p:
        p.return_value.json.return_value = {"ok": True, "result": {"message_id": 55}}
        p.return_value.status_code = 200
        result = dispatcher.send({"text": "h", "reply_markup": {}}, _c(), mem)
    assert result == 99
