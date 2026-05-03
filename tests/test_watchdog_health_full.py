"""tests/test_watchdog_health_full.py — RA-1910 phase 1.

Coverage for the /api/health/full watchdog poller:

  * silent when all components green (no Telegram sends)
  * fires Telegram alert on first red sighting + bumps cooldown
  * cooldown blocks repeat alerts within 30 minutes
  * sends recovery message exactly once when component flips red→green
  * cooldown is per-component (one component's cooldown does not silence another)
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import pytest

import app.server.cron_watchdogs as cw


@pytest.fixture(autouse=True)
def _reset_state():
    cw._health_alert_cooldowns.clear()
    cw._health_red_components.clear()
    yield
    cw._health_alert_cooldowns.clear()
    cw._health_red_components.clear()


class _StubResp:
    def __init__(self, body: dict):
        self._body = json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self._body


def _patch_fetch(monkeypatch, body: dict) -> None:
    """Patch urllib.request.urlopen to return ``body``."""
    import urllib.request as _ureq

    def fake_urlopen(req, timeout=5):  # noqa: ARG001
        return _StubResp(body)

    monkeypatch.setattr(_ureq, "urlopen", fake_urlopen)


def _patch_fetch_raises(monkeypatch) -> None:
    import urllib.request as _ureq

    def fake_urlopen(req, timeout=5):  # noqa: ARG001
        raise OSError("connection refused")

    monkeypatch.setattr(_ureq, "urlopen", fake_urlopen)


@pytest.fixture
def _capture_telegram(monkeypatch):
    """Capture every Telegram send from the watchdog, drop the real network call."""
    sent: list[str] = []

    def fake_send(text: str, log) -> None:  # noqa: ARG001
        sent.append(text)

    monkeypatch.setattr(cw, "_health_full_send_telegram", fake_send)
    return sent


@pytest.mark.asyncio
async def test_silent_when_all_green(_capture_telegram, monkeypatch):
    body = {
        "ok": True,
        "components": {
            "hermes_gateway":   {"ok": True},
            "pi_ceo_railway":   {"ok": True},
            "margot_route":     {"ok": True},
            "mcp_pi_ceo":       {"ok": True},
            "openrouter":       {"ok": True},
            "supabase":         {"ok": True},
            "telegram_polling": {"ok": True},
        },
    }
    _patch_fetch(monkeypatch, body)
    await cw._watchdog_health_full(logging.getLogger("test"))

    assert _capture_telegram == []
    assert cw._health_alert_cooldowns == {}
    assert cw._health_red_components == set()


@pytest.mark.asyncio
async def test_alerts_on_first_red_then_cooldown_blocks(_capture_telegram, monkeypatch):
    body = {
        "ok": False,
        "components": {
            "hermes_gateway":   {"ok": True},
            "pi_ceo_railway":   {"ok": True},
            "margot_route":     {"ok": True},
            "mcp_pi_ceo":       {"ok": True},
            "openrouter":       {"ok": False, "error": "down"},
            "supabase":         {"ok": True},
            "telegram_polling": {"ok": True},
        },
    }
    _patch_fetch(monkeypatch, body)

    await cw._watchdog_health_full(logging.getLogger("test"))
    assert len(_capture_telegram) == 1
    assert "openrouter" in _capture_telegram[0]
    assert "openrouter" in cw._health_alert_cooldowns
    assert cw._health_red_components == {"openrouter"}

    # Second tick within cooldown — no new alert.
    await cw._watchdog_health_full(logging.getLogger("test"))
    assert len(_capture_telegram) == 1


@pytest.mark.asyncio
async def test_recovery_message_sent_when_component_flips_back(_capture_telegram, monkeypatch):
    red_body = {
        "ok": False,
        "components": {
            "hermes_gateway":   {"ok": True},
            "pi_ceo_railway":   {"ok": True},
            "margot_route":     {"ok": True},
            "mcp_pi_ceo":       {"ok": True},
            "openrouter":       {"ok": False, "error": "down"},
            "supabase":         {"ok": True},
            "telegram_polling": {"ok": True},
        },
    }
    _patch_fetch(monkeypatch, red_body)
    await cw._watchdog_health_full(logging.getLogger("test"))
    assert len(_capture_telegram) == 1

    # Now flip openrouter back to green.
    green_body = json.loads(json.dumps(red_body))
    green_body["components"]["openrouter"] = {"ok": True}
    green_body["ok"] = True
    _patch_fetch(monkeypatch, green_body)

    await cw._watchdog_health_full(logging.getLogger("test"))
    assert len(_capture_telegram) == 2
    assert "openrouter" in _capture_telegram[1]
    assert "recovered" in _capture_telegram[1].lower()
    assert "openrouter" not in cw._health_alert_cooldowns
    assert cw._health_red_components == set()


@pytest.mark.asyncio
async def test_per_component_cooldown_isolation(_capture_telegram, monkeypatch):
    """Two components both red simultaneously → both alert. Setting one
    component's cooldown manually must not silence a second, independent
    component going red on a later tick."""
    # First tick: only openrouter red.
    body1 = {
        "components": {
            "hermes_gateway":   {"ok": True},
            "pi_ceo_railway":   {"ok": True},
            "margot_route":     {"ok": True},
            "mcp_pi_ceo":       {"ok": True},
            "openrouter":       {"ok": False, "error": "down"},
            "supabase":         {"ok": True},
            "telegram_polling": {"ok": True},
        },
    }
    _patch_fetch(monkeypatch, body1)
    await cw._watchdog_health_full(logging.getLogger("test"))
    assert len(_capture_telegram) == 1
    assert "openrouter" in _capture_telegram[0]

    # Second tick: openrouter still red (in cooldown) AND supabase newly red.
    body2 = {
        "components": {
            "hermes_gateway":   {"ok": True},
            "pi_ceo_railway":   {"ok": True},
            "margot_route":     {"ok": True},
            "mcp_pi_ceo":       {"ok": True},
            "openrouter":       {"ok": False, "error": "down"},
            "supabase":         {"ok": False, "error": "504"},
            "telegram_polling": {"ok": True},
        },
    }
    _patch_fetch(monkeypatch, body2)
    await cw._watchdog_health_full(logging.getLogger("test"))

    # Exactly one new alert (for supabase). openrouter still in cooldown.
    assert len(_capture_telegram) == 2
    assert "supabase" in _capture_telegram[1]
    assert cw._health_red_components == {"openrouter", "supabase"}


@pytest.mark.asyncio
async def test_fetch_failure_is_silent(_capture_telegram, monkeypatch):
    """If the local /api/health/full call itself errors, the watchdog must
    not raise and must not send Telegram (we don't have a snapshot to act
    on)."""
    _patch_fetch_raises(monkeypatch)
    await cw._watchdog_health_full(logging.getLogger("test"))
    assert _capture_telegram == []
    assert cw._health_red_components == set()
