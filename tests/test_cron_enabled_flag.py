"""TAO_CRON_ENABLED — the cron loop must be suppressible for test servers.

Why this exists: booting the server fires `cron_loop`'s startup catch-up, which
runs REAL work — a full board meeting with live model calls, plus script
triggers that write into `.harness/`. That made `scripts/smoke_test.py`
non-hermetic, and it does the same in CI's `smoke-local` job, which boots a
fresh checkout whose `cron-triggers.json` `last_fired_at` comes straight from
git, so every overdue trigger fires there too.

A gate must measure, not act. These tests pin both directions: the flag must
actually suppress the loop, and — just as important — the default must remain
the current production behaviour, so this change cannot silently switch cron off
in Railway.
"""

import asyncio
import importlib
import os

import pytest


def _reload_config(monkeypatch, value):
    """Reload config with TAO_CRON_ENABLED set (or unset when value is None)."""
    if value is None:
        monkeypatch.delenv("TAO_CRON_ENABLED", raising=False)
    else:
        monkeypatch.setenv("TAO_CRON_ENABLED", value)
    import app.server.config as config

    return importlib.reload(config)


def test_cron_enabled_defaults_to_on(monkeypatch):
    """Unset must mean ON. A flag that defaults off would silently disable
    production cron the moment it merged."""
    config = _reload_config(monkeypatch, None)
    assert config.CRON_ENABLED is True


@pytest.mark.parametrize("value,expected", [
    ("1", True),
    ("0", False),
    ("", False),
    ("true", False),   # only the literal "1" enables, matching PI_SEO_ACTIVE
    ("yes", False),
])
def test_cron_enabled_parses_strictly(monkeypatch, value, expected):
    config = _reload_config(monkeypatch, value)
    assert config.CRON_ENABLED is expected


def test_startup_skips_cron_loop_when_disabled(monkeypatch):
    """The flag must suppress the TASK, not merely be read.

    A test that only asserts `CRON_ENABLED is False` would pass even if
    app_factory ignored it entirely — which is exactly the bug that would let a
    smoke run keep firing board meetings.
    """
    import app.server.app_factory as app_factory

    started: list[str] = []

    def fake_create_task(coro, *args, **kwargs):
        # Close the coroutine so Python does not warn about it never running.
        try:
            coro.close()
        except AttributeError:
            pass

        class _Task:
            def cancel(self):
                pass

        return _Task()

    # Record which loops app_factory decided to start, by name.
    def recording_resilient(fn, name):
        started.append(name)

        async def _noop():
            return None

        return _noop()

    monkeypatch.setattr(app_factory.asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(app_factory, "_resilient", recording_resilient)
    monkeypatch.setattr(app_factory.config, "CRON_ENABLED", False)
    monkeypatch.setattr(app_factory, "restore_sessions", lambda: None)

    asyncio.run(app_factory.on_startup())

    assert "cron_loop" not in started, (
        "cron_loop was started despite TAO_CRON_ENABLED=0 — a test server would "
        "still fire the startup catch-up"
    )
    # Positive control: the other loops still start, so the assertion above is
    # not passing merely because nothing ran at all.
    assert "gc_loop" in started


def test_startup_starts_cron_loop_when_enabled(monkeypatch):
    """The mirror image. Without this, disabling cron everywhere would also
    satisfy the test above."""
    import app.server.app_factory as app_factory

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

    assert "cron_loop" in started


def test_ci_smoke_job_disables_cron():
    """The CI job that boots a server for testing must set the flag.

    Pinning it here means a future edit to ci.yml that drops the env var fails a
    test rather than silently reintroducing live board meetings into CI.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, ".github", "workflows", "ci.yml"), encoding="utf-8") as handle:
        ci = handle.read()

    smoke = ci.split("smoke-local:", 1)
    assert len(smoke) == 2, "smoke-local job not found in ci.yml"
    # Bound the search to this job's env block, not the whole file.
    job = smoke[1].split("steps:", 1)[0]
    assert "TAO_CRON_ENABLED" in job, (
        "smoke-local boots a server for testing but does not disable cron; its "
        "startup catch-up will fire real board meetings and script triggers"
    )
