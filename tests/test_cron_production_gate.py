"""Preview Railway deploys must not run the production cron scheduler.

The scheduler writes to production Supabase and production Linear. Local dev
and tests leave the Railway env vars unset and keep running crons.
TAO_CRON_ALLOW_NON_PRODUCTION=1 is the explicit override.
TAO_CRON_ENABLED=0 still suppresses the loop everywhere.
One predicate (app.server.production_gate) decides this for every startup task that
writes to Linear, Supabase, Telegram or GitHub, not only the cron loop.
"""
from __future__ import annotations

import asyncio
import logging

import pytest

from app.server import cron_scheduler as cs
from app.server import production_gate as pg


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


def _env(monkeypatch, railway_name: str | None, override: bool) -> None:
    _clear(monkeypatch)
    if railway_name is not None:
        monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", railway_name)
    if override:
        monkeypatch.setenv("TAO_CRON_ALLOW_NON_PRODUCTION", "1")


def _record_tasks(monkeypatch, module) -> list[str]:
    """Record the names of background tasks `module` starts, without running them."""
    started: list[str] = []

    def fake_create_task(coro, *args, **kwargs):
        coro.close()

        class _Task:
            def cancel(self):
                pass

        return _Task()

    def recording_resilient(fn, name):
        started.append(name)

        async def _noop():
            return None

        return _noop()

    monkeypatch.setattr(module.asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(module, "_resilient", recording_resilient)
    return started


def _boot(monkeypatch, railway_name: str | None, override: bool = False) -> list[str]:
    """Run startup with the background tasks recorded and not executed."""
    import app.server.app_factory as app_factory
    from app.server import session_model

    _env(monkeypatch, railway_name, override)
    started = _record_tasks(monkeypatch, app_factory)
    monkeypatch.setattr(app_factory.config, "CRON_ENABLED", True)
    monkeypatch.setattr(app_factory, "restore_sessions", lambda: None)
    # Turn every gated task on, so a skip can only come from the production gate.
    monkeypatch.setenv("TAO_SWARM_ENABLED", "1")
    monkeypatch.delenv("TAO_SWARM_INTERNAL_DISABLE", raising=False)
    monkeypatch.setenv("NEXUS_SCHEDULER_ENABLED", "1")

    def fake_recover(*args, **kwargs):
        started.append("supabase_session_recovery")
        return 0

    monkeypatch.setattr(session_model, "recover_interrupted_sessions_from_supabase", fake_recover)
    asyncio.run(app_factory.on_startup())
    return started


def test_startup_skips_crons_on_a_preview(monkeypatch):
    started = _boot(monkeypatch, "pr-908")
    assert "cron_loop" not in started
    assert "gc_loop" in started


def test_startup_runs_crons_in_production(monkeypatch):
    started = _boot(monkeypatch, "production")
    assert "cron_loop" in started


# PC-PDO-PREVIEW-AUTONOMY: preview 05853402 (Pi-Dev-Ops-pr-951, 26/10/2026) ran orphan recovery against
# production Linear and polled production's Telegram bot. Railway names a PR environment "<project>-pr-<n>".
PREVIEW = "Pi-Dev-Ops-pr-951"


# Every startup task in app_factory.on_startup that writes to Linear, Supabase, Telegram or GitHub.
# telegram_intake_loop is started by its own startup hook and is covered below.
GATED_STARTUP_TASKS = [
    "cron_loop",
    "linear_todo_poller",
    "swarm_orchestrator",
    "nexus_scheduler",
    "supabase_session_recovery",
]
# Local, read-only housekeeping that previews keep running.
UNGATED_STARTUP_TASKS = ["gc_loop", "stall_watchdog_loop", "integration_health_loop"]


def test_startup_on_a_preview_starts_no_gated_task(monkeypatch):
    started = _boot(monkeypatch, PREVIEW)
    assert [t for t in GATED_STARTUP_TASKS if t in started] == []
    assert all(t in started for t in UNGATED_STARTUP_TASKS)


@pytest.mark.parametrize("railway_name", ["production", None])
def test_startup_in_production_and_local_dev_starts_every_gated_task(monkeypatch, railway_name):
    # Positive control: the preview test above cannot pass by starting nothing.
    started = _boot(monkeypatch, railway_name)
    assert [t for t in GATED_STARTUP_TASKS if t not in started] == []


def test_override_starts_every_gated_task_on_a_preview(monkeypatch):
    started = _boot(monkeypatch, PREVIEW, override=True)
    assert [t for t in GATED_STARTUP_TASKS if t not in started] == []


def test_every_gated_task_goes_through_the_one_predicate(monkeypatch):
    """The environment check has one owner: flip it and every gated task follows."""
    monkeypatch.setattr(cs, "cron_scheduler_allowed", lambda: False)
    started = _boot(monkeypatch, "production")
    assert [t for t in GATED_STARTUP_TASKS if t in started] == []


def _start_intake(monkeypatch, railway_name: str | None, override: bool = False) -> list[str]:
    """Run the Telegram intake startup hook with the loop recorded and not executed."""
    from app.server.routes import telegram_intake as ti

    _env(monkeypatch, railway_name, override)
    monkeypatch.setenv("TELEGRAM_INTAKE_ENABLED", "1")
    monkeypatch.setattr(ti, "_configured", lambda: True)
    started = _record_tasks(monkeypatch, ti)
    asyncio.run(ti._start_telegram_intake())
    return started


def test_telegram_intake_skips_a_preview(monkeypatch):
    assert _start_intake(monkeypatch, PREVIEW) == []


def test_telegram_intake_runs_in_production(monkeypatch):
    assert _start_intake(monkeypatch, "production") == ["telegram_intake_loop"]


def test_telegram_intake_runs_in_local_dev(monkeypatch):
    assert _start_intake(monkeypatch, None) == ["telegram_intake_loop"]
    assert _start_intake(monkeypatch, PREVIEW, override=True) == ["telegram_intake_loop"]


def test_production_loop_skip_names_the_environment(monkeypatch, caplog):
    _clear(monkeypatch)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", PREVIEW)
    started: list[str] = []
    with caplog.at_level(logging.WARNING):
        assert pg.run_if_production_allowed("demo_loop", lambda: started.append("x"), logging.getLogger("t")) is False
    assert started == []
    assert "demo_loop not started" in caplog.text
    assert PREVIEW in caplog.text


def test_telegram_intake_follows_the_one_predicate(monkeypatch):
    monkeypatch.setattr(cs, "cron_scheduler_allowed", lambda: False)
    assert _start_intake(monkeypatch, "production") == []


def test_production_gate_is_not_a_second_copy_of_the_rule(monkeypatch):
    """production_gate reuses the cron rule: change the rule's answer and the gate follows."""
    _clear(monkeypatch)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", PREVIEW)
    monkeypatch.setattr(cs, "cron_scheduler_allowed", lambda: True)
    assert pg.production_side_effects_allowed() is True
    monkeypatch.setattr(cs, "cron_scheduler_allowed", lambda: False)
    assert pg.production_side_effects_allowed() is False
    assert pg.railway_environment_name() == PREVIEW
