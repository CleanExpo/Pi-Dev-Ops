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
def _reset_state():
    cw._health_alert_cooldowns.clear()
    cw._health_red_components.clear()
    yield
    cw._health_alert_cooldowns.clear()
    cw._health_red_components.clear()


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


# ── Linear find-or-update ───────────────────────────────────────────────────


class _Linear:
    """Fake Linear GraphQL endpoint: records every operation it is sent."""

    def __init__(self, existing: list[dict], labels: list[dict]):
        self.existing = existing
        self.labels = labels
        self.ops: list[tuple[str, dict]] = []

    def urlopen(self, req, timeout=10):  # noqa: ARG002
        payload = json.loads(req.data)
        q = payload["query"]
        v = payload.get("variables") or {}
        if "issueLabels" in q:
            op, data = "labels", {"issueLabels": {"nodes": self.labels}}
        elif "commentCreate" in q:
            op, data = "comment", {"commentCreate": {"success": True}}
        elif "issueCreate" in q:
            op, data = "create", {"issueCreate": {"success": True, "issue": {"identifier": "RA-NEW"}}}
        elif "issues(" in q:
            op, data = "find", {"issues": {"nodes": self.existing}}
        else:
            raise AssertionError(f"unexpected Linear query: {q[:80]}")
        self.ops.append((op, v))
        body = json.dumps({"data": data}).encode()

        class _R:
            def __enter__(self_):
                return self_

            def __exit__(self_, *a):
                return False

            def read(self_):
                return body

        return _R()


@pytest.fixture
def linear_key(monkeypatch):
    import app.server.config as config

    monkeypatch.setattr(config, "LINEAR_API_KEY", "lin_api_test_key", raising=False)


def test_upsert_updates_existing_ticket_never_creates_second(monkeypatch, linear_key):
    import urllib.request as _ureq

    fake = _Linear(existing=[{"id": "uuid-1", "identifier": "RA-9001"}], labels=[])
    monkeypatch.setattr(_ureq, "urlopen", fake.urlopen)

    ident = cw._upsert_red_linear_ticket(
        "[RED] health_full: margot_route", "still red", owner="Margot operator",
        founder_only=False, log=LOG,
    )

    assert ident == "RA-9001"
    kinds = [op for op, _ in fake.ops]
    assert "create" not in kinds
    assert kinds == ["find", "comment"]
    assert fake.ops[1][1]["input"]["issueId"] == "uuid-1"
    assert "Owner: Margot operator" in fake.ops[1][1]["input"]["body"]


def test_upsert_creates_once_with_founder_only_label(monkeypatch, linear_key):
    import urllib.request as _ureq

    fake = _Linear(existing=[], labels=[{"id": "label-fo", "name": "founder-only"}])
    monkeypatch.setattr(_ureq, "urlopen", fake.urlopen)

    ident = cw._upsert_red_linear_ticket(
        "[RED] health_full: schema_drift_db", "SUPABASE_DB_URL not set",
        owner="Deploy/infra operator", founder_only=True, log=LOG,
    )

    assert ident == "RA-NEW"
    creates = [v for op, v in fake.ops if op == "create"]
    assert len(creates) == 1
    inp = creates[0]["input"]
    assert inp["title"] == "[RED] health_full: schema_drift_db"
    assert inp["labelIds"] == ["label-fo"]
    assert "Owner: Deploy/infra operator" in inp["description"]


def test_upsert_agent_fixable_creates_without_label(monkeypatch, linear_key):
    import urllib.request as _ureq

    fake = _Linear(existing=[], labels=[{"id": "label-fo", "name": "founder-only"}])
    monkeypatch.setattr(_ureq, "urlopen", fake.urlopen)

    cw._upsert_red_linear_ticket(
        "[RED] health_full: margot_route", "stale", owner="Margot operator",
        founder_only=False, log=LOG,
    )

    creates = [v for op, v in fake.ops if op == "create"]
    assert len(creates) == 1
    assert "labelIds" not in creates[0]["input"]
    assert "labels" not in [op for op, _ in fake.ops]


def test_upsert_does_not_create_when_lookup_fails(monkeypatch, linear_key):
    """A failed find must not fall through to a create: that is how duplicates are born."""
    import urllib.request as _ureq

    calls: list[str] = []

    def boom(req, timeout=10):  # noqa: ARG001
        calls.append(json.loads(req.data)["query"])
        raise OSError("linear down")

    monkeypatch.setattr(_ureq, "urlopen", boom)

    assert cw._upsert_red_linear_ticket(
        "[RED] health_full: margot_route", "x", owner="o", founder_only=False, log=LOG,
    ) is None
    assert len(calls) == 1
