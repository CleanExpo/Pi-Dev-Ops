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
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_NAME", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)


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
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    monkeypatch.setenv("TELEGRAM_OWNED_BOT_ID", "8720594191")

    class FakeInbox:
        @staticmethod
        def main() -> int:
            calls.append("poll")
            return 0

    monkeypatch.setattr(scripts, "marathon_telegram_inbox", FakeInbox, raising=False)
    monkeypatch.setattr(
        telegram_intake.urllib.request, "urlopen",
        _fake_telegram(requests, bot_id=8720594191),
    )

    asyncio.run(telegram_intake._run_iteration())

    assert calls == []
    assert _methods(requests) == ["getMe", "setWebhook"]
    assert telegram_intake._last_poll_exit == 0
    assert telegram_intake._last_webhook_ok is True
    assert telegram_intake._last_webhook_error == ""


def test_telegram_intake_preview_deploy_never_registers_webhook(monkeypatch):
    """A PR/preview deploy inherits the shared bot token + secret but must not
    call setWebhook — otherwise each ephemeral pr-N host hijacks delivery from
    production. It must fall back to getUpdates polling instead."""
    _clear_webhook_env(monkeypatch)
    calls: list[str] = []
    requests: list[object] = []

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_URL", "https://pr-489.up.railway.app/webhook/telegram")
    monkeypatch.setenv("PHONE_COMPANION_CHAT_ID", "12345")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "pr-489")

    class FakeInbox:
        @staticmethod
        def main() -> int:
            calls.append("poll")
            return 0

    class FakeWatchdog:
        @staticmethod
        def _drain_inbox() -> tuple[int, list[str]]:
            calls.append("drain")
            return 0, []

    def fake_urlopen(req, timeout=0):
        requests.append(req)
        raise AssertionError("preview deploy must never call setWebhook")

    monkeypatch.setattr(scripts, "marathon_telegram_inbox", FakeInbox, raising=False)
    monkeypatch.setattr(scripts, "marathon_watchdog", FakeWatchdog, raising=False)
    monkeypatch.setattr(telegram_intake.urllib.request, "urlopen", fake_urlopen)

    assert telegram_intake._should_use_webhook_mode() is False

    asyncio.run(telegram_intake._run_iteration())

    assert requests == []
    assert calls == ["poll", "drain"]


# ── RA-7434: setWebhook only for the bot this deployment owns ────────────────
#
# PiMargot_bot (7944095471) is polled by the Hermes gateway on the MacBook. If
# its token ever lands on Railway, an unconditional setWebhook silently converts
# the bot to webhook mode and kills that poller. The intake loop must therefore
# ask Telegram who the token belongs to (getMe) and refuse setWebhook unless the
# id equals TELEGRAM_OWNED_BOT_ID. Unset means refuse.


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()


def _method_of(req) -> str:
    return req.full_url.rsplit("/", 1)[-1]


def _methods(requests: list) -> list[str]:
    return [_method_of(r) for r in requests]


def _fake_telegram(requests: list, *, bot_id: int):
    """A mocked Telegram Bot API: answers getMe with ``bot_id``, records everything."""

    def fake_urlopen(req, timeout=0):
        requests.append(req)
        method = _method_of(req)
        if method == "getMe":
            return _FakeResponse({"ok": True, "result": {"id": bot_id, "is_bot": True, "username": "fake_bot"}})
        if method == "setWebhook":
            return _FakeResponse({"ok": True, "description": "Webhook was set"})
        raise AssertionError(f"unexpected Telegram call: {method}")

    return fake_urlopen


def _webhook_env(monkeypatch) -> None:
    _clear_webhook_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_URL", "https://example.test/webhook/telegram")
    monkeypatch.setenv("PHONE_COMPANION_CHAT_ID", "12345")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")


def test_setwebhook_refused_when_getme_id_is_not_the_owned_bot(monkeypatch):
    _webhook_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_OWNED_BOT_ID", "8720594191")
    requests: list = []
    monkeypatch.setattr(
        telegram_intake.urllib.request, "urlopen",
        _fake_telegram(requests, bot_id=7944095471),  # PiMargot_bot — not ours
    )

    ok = telegram_intake._ensure_telegram_webhook()

    assert ok is False
    assert _methods(requests) == ["getMe"], "setWebhook must not be called for a bot we do not own"
    assert telegram_intake._last_webhook_ok is False
    assert "7944095471" in telegram_intake._last_webhook_error
    assert "8720594191" in telegram_intake._last_webhook_error


def test_setwebhook_refused_when_owned_bot_id_is_unset(monkeypatch):
    _webhook_env(monkeypatch)
    monkeypatch.delenv("TELEGRAM_OWNED_BOT_ID", raising=False)
    requests: list = []
    monkeypatch.setattr(
        telegram_intake.urllib.request, "urlopen",
        _fake_telegram(requests, bot_id=8720594191),
    )

    ok = telegram_intake._ensure_telegram_webhook()

    assert ok is False
    assert "setWebhook" not in _methods(requests)
    assert "TELEGRAM_OWNED_BOT_ID" in telegram_intake._last_webhook_error


def test_setwebhook_called_when_getme_id_matches_owned_bot(monkeypatch):
    _webhook_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_OWNED_BOT_ID", "8720594191")
    requests: list = []
    monkeypatch.setattr(
        telegram_intake.urllib.request, "urlopen",
        _fake_telegram(requests, bot_id=8720594191),
    )

    ok = telegram_intake._ensure_telegram_webhook()

    assert ok is True
    assert _methods(requests) == ["getMe", "setWebhook"]
    assert telegram_intake._last_webhook_ok is True
    assert telegram_intake._last_webhook_error == ""


def test_setwebhook_refused_when_getme_fails_no_exception(monkeypatch):
    _webhook_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_OWNED_BOT_ID", "8720594191")
    requests: list = []

    def failing_urlopen(req, timeout=0):
        requests.append(req)
        raise OSError("telegram unreachable")

    monkeypatch.setattr(telegram_intake.urllib.request, "urlopen", failing_urlopen)

    ok = telegram_intake._ensure_telegram_webhook()

    assert ok is False
    assert _methods(requests) == ["getMe"]
    assert "getMe" in telegram_intake._last_webhook_error


def test_run_iteration_skips_setwebhook_on_mismatch_without_raising(monkeypatch):
    _webhook_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_OWNED_BOT_ID", "8720594191")
    requests: list = []
    monkeypatch.setattr(
        telegram_intake.urllib.request, "urlopen",
        _fake_telegram(requests, bot_id=7944095471),
    )

    asyncio.run(telegram_intake._run_iteration())

    assert _methods(requests) == ["getMe"]
    assert telegram_intake._last_poll_exit == 2
    assert telegram_intake._last_error == telegram_intake._last_webhook_error
