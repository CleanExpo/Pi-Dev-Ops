# tests/swarm/pilot/test_scheduler.py
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from swarm.pilot import scheduler


def test_run_cycle_returns_paused_when_paused_hard(monkeypatch):
    monkeypatch.setenv("PILOT_DISABLED", "0")
    monkeypatch.setenv("PILOT_TENANT_SLUG", "phill")
    mem = MagicMock()
    mem.get_pause_state.return_value = "paused-hard"
    with patch("swarm.pilot.scheduler.memory.Memory", return_value=mem), \
         patch("swarm.pilot.scheduler.in_active_window", return_value=True):
        assert scheduler.run_cycle() == "paused"


def test_run_cycle_returns_paused_when_paused_until_future(monkeypatch):
    monkeypatch.setenv("PILOT_DISABLED", "0")
    monkeypatch.setenv("PILOT_TENANT_SLUG", "phill")
    future = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat(timespec="seconds")
    mem = MagicMock()
    mem.get_pause_state.return_value = f"paused-until-{future}"
    with patch("swarm.pilot.scheduler.memory.Memory", return_value=mem), \
         patch("swarm.pilot.scheduler.in_active_window", return_value=True):
        assert scheduler.run_cycle() == "paused"


def test_run_cycle_proceeds_when_paused_until_expired(monkeypatch):
    monkeypatch.setenv("PILOT_DISABLED", "0")
    monkeypatch.setenv("PILOT_TENANT_SLUG", "phill")
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")
    mem = MagicMock()
    mem.get_pause_state.return_value = f"paused-until-{past}"
    mem.pending_count.return_value = 0
    with patch("swarm.pilot.scheduler.memory.Memory", return_value=mem), \
         patch("swarm.pilot.scheduler.in_active_window", return_value=True), \
         patch("swarm.pilot.scheduler.suggester.pick_top", return_value=None):
        assert scheduler.run_cycle() == "no_suggestion"
