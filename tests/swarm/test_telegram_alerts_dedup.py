"""Edge-trigger (dedup_key) behaviour for swarm.telegram_alerts.send.

Mirrors the Guardian RA-6655 fix at the shared send() chokepoint: a persistent
condition pages once; it re-fires only when its state genuinely changes. The
founder has zero tolerance for per-cycle [AGENT OUTPUT] spam.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest

from swarm import telegram_alerts, config


@contextmanager
def _fake_resp():
    class _R:
        def read(self):
            return b'{"ok": true}'
    yield _R()


@pytest.fixture
def wired(monkeypatch, tmp_path):
    """Telegram configured, network stubbed, alert state isolated to tmp."""
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "test-chat")
    monkeypatch.setattr(config, "SWARM_LOG_DIR", tmp_path)
    monkeypatch.setattr(config, "SHADOW_MODE", False, raising=False)

    calls: list[bytes] = []

    def fake_urlopen(req, timeout=10):
        calls.append(req.data)
        return _fake_resp()

    monkeypatch.setattr(telegram_alerts.urllib.request, "urlopen", fake_urlopen)
    return calls


def test_kill_switch_off_suppresses_regardless_of_dedup(monkeypatch, wired):
    monkeypatch.delenv("SWARM_TELEGRAM_ALERTS", raising=False)
    assert telegram_alerts.send("anything", "critical", dedup_key="k") is False
    assert wired == []
    # Kill-switch path must not write dedup state.
    assert not (config.SWARM_LOG_DIR / "telegram_alert_state.json").exists()


def test_without_dedup_key_sends_every_time(monkeypatch, wired):
    monkeypatch.setenv("SWARM_TELEGRAM_ALERTS", "1")
    assert telegram_alerts.send("repeat", "high") is True
    assert telegram_alerts.send("repeat", "high") is True
    assert len(wired) == 2


def test_dedup_suppresses_unchanged_repeat(monkeypatch, wired):
    monkeypatch.setenv("SWARM_TELEGRAM_ALERTS", "1")
    assert telegram_alerts.send("Ollama not responding", "critical", dedup_key="guardian") is True
    assert telegram_alerts.send("Ollama not responding", "critical", dedup_key="guardian") is False
    assert telegram_alerts.send("Ollama not responding", "critical", dedup_key="guardian") is False
    assert len(wired) == 1


def test_volatile_numbers_ignored(monkeypatch, wired):
    monkeypatch.setenv("SWARM_TELEGRAM_ALERTS", "1")
    assert telegram_alerts.send("log 3.2h old", "high", dedup_key="stale") is True
    # Same condition, drifted number — must not re-page.
    assert telegram_alerts.send("log 3.9h old", "high", dedup_key="stale") is False
    assert len(wired) == 1


def test_changed_condition_refires(monkeypatch, wired):
    monkeypatch.setenv("SWARM_TELEGRAM_ALERTS", "1")
    assert telegram_alerts.send("Ollama down", "critical", dedup_key="g") is True
    assert telegram_alerts.send("Disk full", "critical", dedup_key="g") is True
    assert len(wired) == 2


def test_severity_change_refires(monkeypatch, wired):
    monkeypatch.setenv("SWARM_TELEGRAM_ALERTS", "1")
    assert telegram_alerts.send("queue backlog", "high", dedup_key="q") is True
    assert telegram_alerts.send("queue backlog", "critical", dedup_key="q") is True
    assert len(wired) == 2


def test_distinct_keys_are_independent(monkeypatch, wired):
    monkeypatch.setenv("SWARM_TELEGRAM_ALERTS", "1")
    assert telegram_alerts.send("same body", "info", dedup_key="a") is True
    assert telegram_alerts.send("same body", "info", dedup_key="b") is True
    assert len(wired) == 2


def test_failed_send_does_not_record_state(monkeypatch, wired):
    monkeypatch.setenv("SWARM_TELEGRAM_ALERTS", "1")

    def boom(req, timeout=10):
        raise OSError("network down")

    monkeypatch.setattr(telegram_alerts.urllib.request, "urlopen", boom)
    assert telegram_alerts.send("flaky", "high", dedup_key="f") is False
    # State never recorded, so a later successful send still fires.
    monkeypatch.setattr(telegram_alerts.urllib.request, "urlopen",
                        lambda req, timeout=10: _fake_resp())
    assert telegram_alerts.send("flaky", "high", dedup_key="f") is True
    assert len(wired) == 0  # original counter saw no successful call
