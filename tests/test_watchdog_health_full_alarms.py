"""tests/test_watchdog_health_full_alarms.py — audit 2026-09-30 rank #6.

The /api/health/full watchdog was silent in production for a month while
margot_route sat red:

  * it polled 127.0.0.1:8000 while uvicorn binds PORT (8080 on Railway);
  * /api/health/full answers 503 when anything is red, urlopen raises
    HTTPError on a 503, and the watchdog dropped that body into log.debug —
    so the one response that carried the alarm was the one it discarded.

It also only ever pinged Telegram. A red guard now finds-or-updates ONE
Linear ticket with a named owner, labelled founder-only when the fix needs
something only the founder can grant. Linear and Telegram are mocked here;
nothing leaves the process.
"""
from __future__ import annotations

import io
import json
import logging

import pytest

import app.server.cron_watchdogs as cw

LOG = logging.getLogger("test")


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    monkeypatch.setattr("app.server.red_signals._poll_failures", 0)
    cw._health_alert_cooldowns.clear()
    cw._health_red_components.clear()
    cw._health_ticket_unfiled.clear()
    yield
    cw._health_alert_cooldowns.clear()
    cw._health_red_components.clear()
    cw._health_ticket_unfiled.clear()


def _red_body(component: str = "margot_route", error: str = "no turn since 2026-08-30") -> dict:
    return {
        "ok": False,
        "red_components": [component],
        "components": {
            "hermes_gateway": {"ok": True},
            component: {"ok": False, "status": "stale", "error": error},
        },
    }


def _http_503(url: str, body: dict):
    import urllib.error

    return urllib.error.HTTPError(
        url, 503, "Service Unavailable", {}, io.BytesIO(json.dumps(body).encode())
    )


@pytest.fixture
def telegram(monkeypatch):
    """Mock the real swarm send so the whole watchdog→Telegram path runs."""
    import swarm.telegram_alerts as ta

    sent: list[dict] = []

    def fake_send(message, severity="info", bot_name="Swarm", dedup_key=None):
        sent.append({"message": message, "severity": severity, "bot_name": bot_name})
        return True

    monkeypatch.setattr(ta, "send", fake_send)
    return sent


@pytest.fixture
def tickets(monkeypatch):
    calls: list[dict] = []

    def fake_upsert(title, body, *, owner, founder_only, log):  # noqa: ARG001
        calls.append({"title": title, "body": body, "owner": owner, "founder_only": founder_only})
        return "RA-TEST"

    monkeypatch.setattr(cw, "_upsert_red_linear_ticket", fake_upsert)
    return calls


def _serve_503(monkeypatch, body: dict, seen_urls: list[str]) -> None:
    import urllib.request as _ureq

    def fake_urlopen(req, timeout=5):  # noqa: ARG001
        url = req.full_url if hasattr(req, "full_url") else str(req)
        seen_urls.append(url)
        raise _http_503(url, body)

    monkeypatch.setattr(_ureq, "urlopen", fake_urlopen)


# ── port ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("port_env,expected", [(None, "8080"), ("8080", "8080"), ("9123", "9123")])
async def test_polls_the_port_uvicorn_binds(monkeypatch, telegram, tickets, port_env, expected):
    if port_env is None:
        monkeypatch.delenv("PORT", raising=False)
    else:
        monkeypatch.setenv("PORT", port_env)
    urls: list[str] = []
    _serve_503(monkeypatch, _red_body(), urls)

    await cw._watchdog_health_full(LOG)

    assert urls == [f"http://127.0.0.1:{expected}/api/health/full"]


# ── the 503 carries the alarm ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_503_with_red_component_sends_telegram(monkeypatch, telegram, tickets):
    monkeypatch.delenv("PORT", raising=False)
    _serve_503(monkeypatch, _red_body("margot_route"), [])

    await cw._watchdog_health_full(LOG)

    assert len(telegram) == 1, telegram
    assert "margot_route" in telegram[0]["message"]
    assert cw._health_red_components == {"margot_route"}


@pytest.mark.asyncio
async def test_linear_ticket_write_runs_off_the_event_loop(monkeypatch, telegram):
    # The Linear upsert is sync urllib; on the loop it would stall every other task.
    import threading
    monkeypatch.delenv("PORT", raising=False)
    _serve_503(monkeypatch, _red_body("margot_route"), [])
    seen: dict = {"loop": threading.get_ident()}

    def fake_upsert(title, body, *, owner, founder_only, log):  # noqa: ARG001
        seen["upsert"] = threading.get_ident()
        return "RA-TEST"

    monkeypatch.setattr(cw, "_upsert_red_linear_ticket", fake_upsert)
    await cw._watchdog_health_full(LOG)
    assert "upsert" in seen and seen["upsert"] != seen["loop"]


@pytest.mark.asyncio
async def test_503_with_red_component_upserts_one_owned_ticket(monkeypatch, telegram, tickets):
    monkeypatch.delenv("PORT", raising=False)
    _serve_503(monkeypatch, _red_body("margot_route"), [])

    await cw._watchdog_health_full(LOG)
    # Second tick inside cooldown: no second Telegram, no second upsert.
    await cw._watchdog_health_full(LOG)

    assert len(tickets) == 1
    assert tickets[0]["title"] == "[RED] health_full: margot_route"
    assert tickets[0]["owner"] == "Margot operator"
    assert tickets[0]["founder_only"] is False


@pytest.mark.asyncio
async def test_credential_red_is_founder_only(monkeypatch, telegram, tickets):
    monkeypatch.delenv("PORT", raising=False)
    _serve_503(monkeypatch, _red_body("schema_drift_db", error="SUPABASE_DB_URL not set"), [])

    await cw._watchdog_health_full(LOG)

    assert tickets and tickets[0]["founder_only"] is True


@pytest.mark.asyncio
async def test_non_json_error_is_still_silent(monkeypatch, telegram, tickets):
    import urllib.error
    import urllib.request as _ureq

    def fake_urlopen(req, timeout=5):  # noqa: ARG001
        raise urllib.error.HTTPError(req.full_url, 502, "Bad Gateway", {}, io.BytesIO(b"<html>"))

    monkeypatch.setattr(_ureq, "urlopen", fake_urlopen)
    await cw._watchdog_health_full(LOG)
    assert telegram == [] and tickets == []


@pytest.mark.asyncio
async def test_failed_ticket_write_retries_next_tick(monkeypatch, telegram):
    """Review round 2: a failed upsert must not wait out the Telegram cooldown."""
    monkeypatch.delenv("PORT", raising=False)
    _serve_503(monkeypatch, _red_body("margot_route"), [])
    results = [None, "RA-9001"]
    calls: list[str] = []

    def flaky_upsert(title, body, *, owner, founder_only, log):  # noqa: ARG001
        calls.append(title)
        return results[len(calls) - 1] if len(calls) <= len(results) else "RA-9001"

    monkeypatch.setattr(cw, "_upsert_red_linear_ticket", flaky_upsert)

    await cw._watchdog_health_full(LOG)   # upsert fails
    await cw._watchdog_health_full(LOG)   # inside cooldown: retried, succeeds
    await cw._watchdog_health_full(LOG)   # filed: no further write this cooldown

    assert len(calls) == 2
    assert len(telegram) == 1
    assert cw._health_ticket_unfiled == set()


@pytest.mark.asyncio
async def test_degraded_unobserved_component_is_not_red(monkeypatch, telegram, tickets):
    """Review round 4: /api/health/full answers 200 with red_components=[] when a
    component is merely unobserved on this host. That is not a red guard."""
    monkeypatch.delenv("PORT", raising=False)
    import urllib.request as _ureq

    body = {
        "ok": True, "red_components": [], "degraded_components": ["hermes_gateway"],
        "components": {"hermes_gateway": {"ok": False, "observed": False, "status": "not_observed"}},
    }

    class _R:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(body).encode()

    monkeypatch.setattr(_ureq, "urlopen", lambda req, timeout=5: _R())
    await cw._watchdog_health_full(LOG)
    assert telegram == [] and tickets == []


@pytest.mark.parametrize("error,expected", [
    ("credential expired", True),
    ("SUPABASE_DB_URL absent", True),
    ("[Errno 13] Permission denied: .harness/hermes/heartbeat.jsonl", False),
    ("HTTP 403 Forbidden", True),
    ("HTTP 401 unauthorized", True),
    ("last token count stale", False),
    ("no turn since 2026-08-30", False),
    ("missing llm-cost log", False),
    ("missing conversation record", False),
    ("missing TELEGRAM_BOT_TOKEN or TELEGRAM_WEBHOOK_SECRET", True),
])
def test_founder_only_classification(error, expected):
    from app.server.red_signals import health_full_ticket

    assert health_full_ticket("supabase", {"ok": False, "error": error})["founder_only"] is expected


@pytest.mark.asyncio
@pytest.mark.parametrize("unobserved_payload", [
    {"ok": False, "observed": False, "status": "not_observed"},
    {"ok": True, "observed": False, "status": "not_observed"},
    {"ok": True, "status": "not_observed"},  # round 7: status-only
])
async def test_red_turning_unobserved_is_not_announced_green(monkeypatch, telegram, tickets, unobserved_payload):
    """Review rounds 5-6: red -> not_observed is unresolved, not a recovery, whatever ok says."""
    monkeypatch.delenv("PORT", raising=False)
    _serve_503(monkeypatch, _red_body("margot_route"), [])
    await cw._watchdog_health_full(LOG)

    import urllib.request as _ureq

    unobserved = {
        "ok": True, "red_components": [], "degraded_components": ["margot_route"],
        "components": {"margot_route": unobserved_payload},
    }

    class _R:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(unobserved).encode()

    monkeypatch.setattr(_ureq, "urlopen", lambda req, timeout=5: _R())
    await cw._watchdog_health_full(LOG)

    assert not any("recovered" in m["message"] for m in telegram)
    assert cw._health_red_components == {"margot_route"}
