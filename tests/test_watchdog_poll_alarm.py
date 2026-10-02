"""tests/test_watchdog_poll_alarm.py — the /api/health/full poll is itself a guard.

#869 put /api/health/full behind auth. A watchdog whose poll is refused, or
that cannot reach the route at all, used to log a WARNING and return — the
alarm system went quiet exactly when it could no longer see. The poll is now
reported as the component ``health_full_watchdog``: red at once on an auth
refusal, red after POLL_FAILURES_TO_RED failures in a row otherwise, and
recovered by the next good poll. Telegram and Linear are mocked.
"""
from __future__ import annotations

import io
import json
import logging
import urllib.error
import urllib.request as _ureq

import pytest

import app.server.cron_watchdogs as cw
import app.server.red_signals as rs

LOG = logging.getLogger("test")
WD = rs.WATCHDOG_COMPONENT


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(rs, "_poll_failures", 0)
    for state in (cw._health_alert_cooldowns, cw._health_red_components, cw._health_ticket_unfiled):
        state.clear()
    yield
    for state in (cw._health_alert_cooldowns, cw._health_red_components, cw._health_ticket_unfiled):
        state.clear()


@pytest.fixture
def alerts(monkeypatch):
    import swarm.telegram_alerts as ta

    sent: list[str] = []
    tickets: list[dict] = []
    monkeypatch.setattr(ta, "send", lambda message, **_: sent.append(message) or True)

    def fake_upsert(title, body, *, owner, founder_only, log):  # noqa: ARG001
        tickets.append({"title": title, "founder_only": founder_only})
        return "RA-TEST"

    monkeypatch.setattr(cw, "_upsert_red_linear_ticket", fake_upsert)
    return sent, tickets


def _raise(exc_factory):
    def fake_urlopen(req, timeout=5):  # noqa: ARG001
        raise exc_factory(req.full_url)
    return fake_urlopen


def _http(code: int, body: bytes = b"{}"):
    return lambda url: urllib.error.HTTPError(url, code, "x", {}, io.BytesIO(body))


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [401, 403])
async def test_auth_refusal_is_red_at_once(monkeypatch, alerts, code):
    sent, tickets = alerts
    monkeypatch.setattr(_ureq, "urlopen", _raise(_http(code)))
    await cw._watchdog_health_full(LOG)
    assert cw._health_red_components == {WD}
    assert len(sent) == 1 and WD in sent[0] and str(code) in sent[0]
    assert len(tickets) == 1 and tickets[0]["founder_only"] is True


@pytest.mark.asyncio
async def test_session_that_cannot_be_minted_is_red_at_once(monkeypatch, alerts):
    import app.server.auth as auth

    def broken():
        raise RuntimeError("TAO_PASSWORD unset")

    monkeypatch.setattr(auth, "create_session_token", broken)
    await cw._watchdog_health_full(LOG)
    assert cw._health_red_components == {WD}
    assert len(alerts[0]) == 1


@pytest.mark.asyncio
async def test_unreachable_poll_is_red_only_after_repeated_failures(monkeypatch, alerts):
    sent, _ = alerts
    monkeypatch.setattr(_ureq, "urlopen", _raise(lambda url: OSError("connection refused")))
    for _ in range(rs.POLL_FAILURES_TO_RED - 1):
        await cw._watchdog_health_full(LOG)
    assert sent == [] and cw._health_red_components == set()
    await cw._watchdog_health_full(LOG)
    assert cw._health_red_components == {WD} and len(sent) == 1


@pytest.mark.asyncio
async def test_good_poll_recovers_the_poll_alarm(monkeypatch, alerts):
    sent, _ = alerts
    monkeypatch.setattr(_ureq, "urlopen", _raise(_http(401)))
    await cw._watchdog_health_full(LOG)
    green = {"ok": True, "red_components": [], "components": {"hermes_gateway": {"ok": True}}}

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(_ureq, "urlopen", lambda req, timeout=5: _Resp(json.dumps(green).encode()))
    await cw._watchdog_health_full(LOG)
    assert cw._health_red_components == set()
    assert any("recovered" in m and WD in m for m in sent), sent
