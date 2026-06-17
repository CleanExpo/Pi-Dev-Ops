from __future__ import annotations

import asyncio

import scripts
from app.server.routes import telegram_intake


def test_telegram_intake_reports_configured_with_phone_chat(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.delenv("ALLOWED_USERS", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setenv("PHONE_COMPANION_CHAT_ID", "12345")

    status = telegram_intake._status()

    assert status["enabled"] is True
    assert status["configured"] is True
    assert status["has_bot_token"] is True
    assert status["has_chat_allowlist"] is True


def test_telegram_intake_iteration_polls_then_drains(monkeypatch):
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
