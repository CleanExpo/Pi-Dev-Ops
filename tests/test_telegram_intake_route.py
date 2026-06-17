from __future__ import annotations

import asyncio
import json

import scripts
from app.server.routes import telegram_intake


def _clear_webhook_env(monkeypatch):
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("TELEGRAM_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("TELEGRAM_WEBHOOK_AUTOCONFIGURE", raising=False)
    monkeypatch.delenv("PI_CEO_PUBLIC_URL", raising=False)
    monkeypatch.delenv("PI_CEO_URL", raising=False)
    monkeypatch.delenv("RAILWAY_PUBLIC_DOMAIN", raising=False)


def test_telegram_intake_reports_configured_with_phone_chat(monkeypatch):
    _clear_webhook_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.delenv("ALLOWED_USERS", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setenv("PHONE_COMPANION_CHAT_ID", "12345")

    status = telegram_intake._status()

    assert status["enabled"] is True
    assert status["configured"] is True
    assert status["has_bot_token"] is True
    assert status["has_chat_allowlist"] is True
    assert status["webhook_mode"] is False


def test_telegram_intake_iteration_polls_then_drains(monkeypatch):
    _clear_webhook_env(monkeypatch)
    calls: list[str] = []

    class FakeInbox:
        @staticmethod
        def main() -> int:
            calls.append("poll")
            return 0

    class FakeWatchdog:
        @staticmethod
        def _drain_inbox() -> tuple[int, list[str]]:
            calls.append("drain")
            return 1, ["queued"]

    monkeypatch.setattr(scripts, "marathon_telegram_inbox", FakeInbox, raising=False)
    monkeypatch.setattr(scripts, "marathon_watchdog", FakeWatchdog, raising=False)

    asyncio.run(telegram_intake._run_iteration())

    assert calls == ["poll", "drain"]
    assert telegram_intake._last_poll_exit == 0
    assert telegram_intake._last_processed == 1


def test_telegram_intake_webhook_mode_sets_webhook_and_skips_poll(monkeypatch):
    calls: list[str] = []
    requests: list[object] = []

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_URL", "https://example.test/webhook/telegram")
    monkeypatch.setenv("PHONE_COMPANION_CHAT_ID", "12345")

    class FakeInbox:
        @staticmethod
        def main() -> int:
            calls.append("poll")
            return 0

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        @staticmethod
        def read() -> bytes:
            return json.dumps({"ok": True, "description": "Webhook was set"}).encode()

    def fake_urlopen(req, timeout=0):
        requests.append(req)
        return FakeResponse()

    monkeypatch.setattr(scripts, "marathon_telegram_inbox", FakeInbox, raising=False)
    monkeypatch.setattr(telegram_intake.urllib.request, "urlopen", fake_urlopen)

    asyncio.run(telegram_intake._run_iteration())

    assert calls == []
    assert len(requests) == 1
    assert telegram_intake._last_poll_exit == 0
    assert telegram_intake._last_webhook_ok is True
    assert telegram_intake._last_webhook_error == ""
