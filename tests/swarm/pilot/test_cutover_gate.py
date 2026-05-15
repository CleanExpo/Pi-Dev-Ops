# tests/swarm/pilot/test_cutover_gate.py
from datetime import datetime, timezone
from unittest.mock import patch
from swarm.pilot.scripts import cutover_gate


def test_gate_blocks_before_cutover_window():
    before = datetime(2026, 5, 19, 7, 59, tzinfo=timezone.utc)  # 1 min before
    with patch("swarm.pilot.scripts.cutover_gate.datetime") as dt:
        dt.now.return_value = before
        assert cutover_gate.is_open() is False


def test_gate_opens_at_cutover_window():
    at_window = datetime(2026, 5, 19, 8, 0, tzinfo=timezone.utc)  # exactly at window
    with patch("swarm.pilot.scripts.cutover_gate.datetime") as dt:
        dt.now.return_value = at_window
        assert cutover_gate.is_open() is True


def test_gate_opens_after_cutover_window():
    after = datetime(2026, 5, 19, 9, 0, tzinfo=timezone.utc)  # 1h after
    with patch("swarm.pilot.scripts.cutover_gate.datetime") as dt:
        dt.now.return_value = after
        assert cutover_gate.is_open() is True


def test_cutover_at_constant_is_correct_timestamp():
    """2026-05-19T08:00Z == Tue 19 May 2026 18:00 AEST (UTC+10)."""
    assert cutover_gate.CUTOVER_AT == datetime(2026, 5, 19, 8, 0, tzinfo=timezone.utc)


def test_main_returns_1_before_window():
    before = datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)
    with patch("swarm.pilot.scripts.cutover_gate.datetime") as dt:
        dt.now.return_value = before
        assert cutover_gate.main() == 1


def test_main_returns_0_after_window():
    after = datetime(2026, 5, 20, 0, 0, tzinfo=timezone.utc)
    with patch("swarm.pilot.scripts.cutover_gate.datetime") as dt:
        dt.now.return_value = after
        assert cutover_gate.main() == 0
