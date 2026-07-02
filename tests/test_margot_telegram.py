"""Tests for swarm.margot_telegram — per-chat Bot API delivery."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from swarm import margot_telegram as mt


def test_send_margot_reply_without_token_logs_only(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    ok = mt.send_margot_reply(chat_id="1", text="hello")
    assert ok is False


def test_send_margot_reply_posts_message(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    calls: list[tuple[str, dict]] = []

    def fake_post_json(token, method, payload):
        calls.append((method, payload))
        return True

    monkeypatch.setattr(mt, "_post_json", fake_post_json)
    ok = mt.send_margot_reply(chat_id="99", text="Margot says hi", reply_to_message_id="7")
    assert ok is True
    assert calls[0][0] == "sendMessage"
    assert calls[0][1]["chat_id"] == "99"
    assert calls[0][1]["reply_to_message_id"] == "7"


def test_send_margot_reply_attaches_voice(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    audio = tmp_path / "reply.mp3"
    audio.write_bytes(b"\xff\xfb")  # minimal mp3-ish bytes

    voice_calls: list[str] = []
    monkeypatch.setattr(
        mt, "_post_multipart",
        lambda token, method, fields, **kw: voice_calls.append(method) or True,
    )
    monkeypatch.setattr(mt, "_post_json", lambda *a, **k: True)

    ok = mt.send_margot_reply(chat_id="5", text="voice + text", audio_path=audio)
    assert ok is True
    assert voice_calls == ["sendVoice"]
