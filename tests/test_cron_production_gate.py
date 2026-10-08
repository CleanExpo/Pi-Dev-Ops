"""Preview Railway deploys must not run the production cron scheduler.

The scheduler writes to production Supabase and production Linear. Local dev
and tests leave the Railway env vars unset and keep running crons.
TAO_CRON_ALLOW_NON_PRODUCTION=1 is the explicit override.
TAO_CRON_ENABLED=0 still suppresses the loop everywhere.
"""
from __future__ import annotations

import asyncio
import logging

import pytest

from app.server import cron_scheduler as cs


def _clear(monkeypatch) -> None:
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_NAME", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("TAO_CRON_ALLOW_NON_PRODUCTION", raising=False)


def test_local_dev_runs_the_scheduler(monkeypatch):
    _clear(monkeypatch)
    assert cs.cron_scheduler_allowed() is True
    assert cs.railway_cron_environment() == ""


def test_production_name_runs_the_scheduler(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "00000000-0000-0000-0000-000000000001")
    assert cs.cron_scheduler_allowed() is True


def test_environment_name_is_stripped_and_case_insensitive(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", " Production ")
    assert cs.cron_scheduler_allowed() is True


def test_preview_environment_does_not_run_the_scheduler(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "pr-904")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    assert cs.cron_scheduler_allowed() is False


@pytest.mark.parametrize("name", ["pr-906", "pr-907", "pr-908"])
def test_named_previews_are_blocked(monkeypatch, name):
    _clear(monkeypatch)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", name)
    assert cs.cron_scheduler_allowed() is False


def test_railway_environment_fallback_when_name_is_unset(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "pr-907")
    assert cs.cron_scheduler_allowed() is False
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    assert cs.cron_scheduler_allowed() is True


def test_override_allows_a_preview(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "pr-906")
    monkeypatch.setenv("TAO_CRON_ALLOW_NON_PRODUCTION", "1")
    assert cs.cron_scheduler_allowed() is True


@pytest.mark.parametrize("value", ["", "0", "true", "yes"])
def test_override_is_only_the_literal_1(monkeypatch, value):
    _clear(monkeypatch)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "pr-904")
    monkeypatch.setenv("TAO_CRON_ALLOW_NON_PRODUCTION", value)
    assert cs.cron_scheduler_allowed() is False


def test_preview_skip_is_logged_and_does_not_start(monkeypatch, caplog):
    _clear(monkeypatch)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "pr-904")
    from app.server import config

    monkeypatch.setattr(config, "CRON_ENABLED", True)
    started: list[object] = []
    log = logging.getLogger("test-cron-gate")
    with caplog.at_level(logging.WARNING):
        cs.maybe_start_cron_loop(started.append, log)
    assert started == []
    assert "pr-904" in caplog.text
    assert "not production" in caplog.text


def test_production_starts_the_loop(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    from app.server import config

    monkeypatch.setattr(config, "CRON_ENABLED", True)
    started: list[object] = []
    cs.maybe_start_cron_loop(started.append, logging.getLogger("test-cron-gate"))
    assert started == [cs.cron_loop]


def test_local_dev_starts_the_loop(monkeypatch):
    _clear(monkeypatch)
    from app.server import config

    monkeypatch.setattr(config, "CRON_ENABLED", True)
    started: list[object] = []
    cs.maybe_start_cron_loop(started.append, logging.getLogger("test-cron-gate"))
    assert started == [cs.cron_loop]


def test_cron_enabled_flag_still_suppresses_a_preview_override(monkeypatch, caplog):
    _clear(monkeypatch)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "pr-904")
    monkeypatch.setenv("TAO_CRON_ALLOW_NON_PRODUCTION", "1")
    from app.server import config

    monkeypatch.setattr(config, "CRON_ENABLED", False)
    started: list[object] = []
    log = logging.getLogger("test-cron-gate")
    with caplog.at_level(logging.INFO):
        cs.maybe_start_cron_loop(started.append, log)
    assert started == []
    assert "TAO_CRON_ENABLED=0" in caplog.text


def _boot(monkeypatch, railway_name: str | None) -> list[str]:
    """Run startup with the cron task recorded and not executed."""
    import app.server.app_factory as app_factory

    if railway_name is None:
        monkeypatch.delenv("RAILWAY_ENVIRONMENT_NAME", raising=False)
        monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    else:
        monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", railway_name)
    monkeypatch.delenv("TAO_CRON_ALLOW_NON_PRODUCTION", raising=False)
    started: list[str] = []

    def fake_create_task(coro, *args, **kwargs):
        try:
            coro.close()
        except AttributeError:
            pass

        class _Task:
            def cancel(self):
                pass

        return _Task()

    def recording_resilient(fn, name):
        started.append(name)

        async def _noop():
            return None

        return _noop()

    monkeypatch.setattr(app_factory.asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(app_factory, "_resilient", recording_resilient)
    monkeypatch.setattr(app_factory.config, "CRON_ENABLED", True)
    monkeypatch.setattr(app_factory, "restore_sessions", lambda: None)
    asyncio.run(app_factory.on_startup())
    return started


def test_startup_skips_crons_on_a_preview(monkeypatch):
    started = _boot(monkeypatch, "pr-908")
    assert "cron_loop" not in started
    assert "gc_loop" in started


def test_startup_runs_crons_in_production(monkeypatch):
    started = _boot(monkeypatch, "production")
    assert "cron_loop" in started
