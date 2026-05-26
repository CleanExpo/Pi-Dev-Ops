"""Focused tests for swarm.nexus.scheduler_daemon — pure helpers.

The async loop itself is too big to drive in a unit test (it sleeps
until the next 06:00 UTC); we verify the surrounding helpers — that's
what actually determines correctness for the operator-facing flags.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from swarm.nexus.scheduler_daemon import (
    DEFAULT_SCHEDULER_HOUR,
    RealClock,
    _next_fire_seconds,
    _scheduler_hour,
    _workspaces,
)


class TestSchedulerHour:
    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("NEXUS_SCHEDULER_HOUR", raising=False)
        assert _scheduler_hour() == DEFAULT_SCHEDULER_HOUR

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("NEXUS_SCHEDULER_HOUR", "9")
        assert _scheduler_hour() == 9

    def test_bad_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("NEXUS_SCHEDULER_HOUR", "not-an-int")
        assert _scheduler_hour() == DEFAULT_SCHEDULER_HOUR


class TestWorkspaces:
    def test_empty_env(self, monkeypatch):
        monkeypatch.delenv("NEXUS_SCHEDULER_WORKSPACES", raising=False)
        assert _workspaces() == []

    def test_csv_parsed_and_trimmed(self, monkeypatch):
        monkeypatch.setenv("NEXUS_SCHEDULER_WORKSPACES", " acme , beta , gamma ")
        assert _workspaces() == ["acme", "beta", "gamma"]

    def test_blank_entries_dropped(self, monkeypatch):
        monkeypatch.setenv("NEXUS_SCHEDULER_WORKSPACES", "acme,,beta,")
        assert _workspaces() == ["acme", "beta"]


class TestNextFireSeconds:
    def test_today_target_in_future(self):
        now = datetime(2026, 5, 26, 5, 0, 0, tzinfo=timezone.utc)
        # 06:00 is 1h away
        assert _next_fire_seconds(now, hour=6) == pytest.approx(3600, abs=1)

    def test_target_already_passed_rolls_to_tomorrow(self):
        now = datetime(2026, 5, 26, 7, 0, 0, tzinfo=timezone.utc)
        # 06:00 today already passed → 23h until tomorrow's 06:00
        assert _next_fire_seconds(now, hour=6) == pytest.approx(23 * 3600, abs=1)

    def test_target_exactly_now_rolls_to_tomorrow(self):
        # Strictly after — equal counts as already-fired today.
        now = datetime(2026, 5, 26, 6, 0, 0, tzinfo=timezone.utc)
        assert _next_fire_seconds(now, hour=6) == pytest.approx(24 * 3600, abs=1)


class TestRealClock:
    def test_returns_utc_aware_datetime(self):
        c = RealClock()
        dt = c.now()
        assert dt.tzinfo is not None
        assert dt.tzinfo.utcoffset(dt).total_seconds() == 0


class TestStoreResolution:
    def test_returns_none_when_stores_missing(self, monkeypatch):
        # Simulate the "FastAPI app not booted" scenario.
        import swarm.nexus.scheduler_daemon as daemon

        class _FakeApp:
            class state:
                pass

        class _FakeFactory:
            app = _FakeApp()

        monkeypatch.setitem(__import__("sys").modules, "app.server.app_factory", _FakeFactory)
        assert daemon._resolve_stores() is None
