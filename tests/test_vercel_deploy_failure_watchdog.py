"""
test_vercel_deploy_failure_watchdog.py — RA-1742 watchdog tests.

Locks the contract that the watchdog:
  1. Stays silent if no projects are configured
  2. Stays silent inside the cooldown window
  3. Stays silent when the latest deploy is READY (not ERROR)
  4. Stays silent when the latest deploy is ERROR but younger than threshold
  5. Raises an alert when the latest deploy is ERROR + older than threshold
"""
from __future__ import annotations

import json
import logging
import time
from io import BytesIO
from unittest.mock import patch

import pytest

import app.server.cron_watchdogs as cw


@pytest.fixture(autouse=True)
def _reset_state():
    cw._vercel_deploy_failure_last_raised = 0.0
    yield
    cw._vercel_deploy_failure_last_raised = 0.0


@pytest.fixture
def _hush_network(monkeypatch):
    """Make Telegram + Linear calls silent no-ops."""
    import app.server.config as config
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "", raising=False)
    monkeypatch.setattr(config, "TELEGRAM_ALERT_CHAT_ID", "", raising=False)
    monkeypatch.setattr(config, "LINEAR_API_KEY", "", raising=False)
    monkeypatch.setattr(config, "VERCEL_TOKEN", "fake-token-for-tests", raising=False)


@pytest.fixture
def _one_project(monkeypatch):
    """Stub `_vercel_projects_to_monitor` to return a single fixture project."""
    monkeypatch.setattr(
        cw,
        "_vercel_projects_to_monitor",
        lambda: [{"name": "test-app", "project_id": "prj_test", "team_id": None}],
    )


def _mock_vercel_response(state: str, age_h: float):
    """Build a fake Vercel API response body."""
    return {
        "deployments": [{
            "uid": "dpl_test_abc123def456",
            "url": "test-app-abc.vercel.app",
            "state": state,
            "created": int((time.time() - age_h * 3600) * 1000),
            "meta": {"githubCommitMessage": "test commit"},
        }],
    }


class _FakeUrlOpen:
    def __init__(self, body):
        self._body = body
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self):
        return json.dumps(self._body).encode()


@pytest.mark.asyncio
async def test_silent_when_no_projects_configured(_hush_network, monkeypatch, caplog):
    monkeypatch.setattr(cw, "_vercel_projects_to_monitor", lambda: [])
    with caplog.at_level(logging.WARNING, logger="pi-ceo"):
        await cw._watchdog_vercel_deploy_failures(logging.getLogger("pi-ceo"))
    assert not any("Vercel watchdog" in r.message for r in caplog.records if r.levelno >= logging.WARNING)
    assert cw._vercel_deploy_failure_last_raised == 0.0


@pytest.mark.asyncio
async def test_silent_when_no_vercel_token(monkeypatch, caplog):
    import app.server.config as config
    monkeypatch.setattr(config, "VERCEL_TOKEN", "", raising=False)
    with caplog.at_level(logging.WARNING, logger="pi-ceo"):
        await cw._watchdog_vercel_deploy_failures(logging.getLogger("pi-ceo"))
    assert cw._vercel_deploy_failure_last_raised == 0.0


@pytest.mark.asyncio
async def test_silent_when_latest_deploy_is_ready(_hush_network, _one_project, caplog):
    body = _mock_vercel_response(state="READY", age_h=24)
    with patch("urllib.request.urlopen", return_value=_FakeUrlOpen(body)):
        with caplog.at_level(logging.WARNING, logger="pi-ceo"):
            await cw._watchdog_vercel_deploy_failures(logging.getLogger("pi-ceo"))
    assert not any("Vercel watchdog: 1" in r.message for r in caplog.records)
    assert cw._vercel_deploy_failure_last_raised == 0.0


@pytest.mark.asyncio
async def test_silent_when_error_younger_than_threshold(_hush_network, _one_project, caplog):
    # ERROR but only 30 min old — under the 2 h threshold.
    body = _mock_vercel_response(state="ERROR", age_h=0.5)
    with patch("urllib.request.urlopen", return_value=_FakeUrlOpen(body)):
        with caplog.at_level(logging.WARNING, logger="pi-ceo"):
            await cw._watchdog_vercel_deploy_failures(logging.getLogger("pi-ceo"))
    assert not any("Vercel watchdog: 1" in r.message for r in caplog.records)
    assert cw._vercel_deploy_failure_last_raised == 0.0


@pytest.mark.asyncio
async def test_alerts_when_error_older_than_threshold(_hush_network, _one_project, caplog):
    # 4 h old ERROR — well over the 2 h threshold.
    body = _mock_vercel_response(state="ERROR", age_h=4.0)
    before = cw._vercel_deploy_failure_last_raised
    with patch("urllib.request.urlopen", return_value=_FakeUrlOpen(body)):
        with caplog.at_level(logging.WARNING, logger="pi-ceo"):
            await cw._watchdog_vercel_deploy_failures(logging.getLogger("pi-ceo"))
    assert any(
        "1 project(s) have stale ERROR" in r.message for r in caplog.records
    ), "Expected the warning log when stale ERROR detected"
    assert cw._vercel_deploy_failure_last_raised > before


@pytest.mark.asyncio
async def test_cooldown_suppresses_subsequent_calls(_hush_network, _one_project):
    body = _mock_vercel_response(state="ERROR", age_h=4.0)
    with patch("urllib.request.urlopen", return_value=_FakeUrlOpen(body)):
        await cw._watchdog_vercel_deploy_failures(logging.getLogger("pi-ceo"))
    first = cw._vercel_deploy_failure_last_raised
    assert first > 0

    with patch("urllib.request.urlopen", return_value=_FakeUrlOpen(body)):
        await cw._watchdog_vercel_deploy_failures(logging.getLogger("pi-ceo"))
    assert cw._vercel_deploy_failure_last_raised == first
