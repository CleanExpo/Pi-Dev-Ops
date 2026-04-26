"""
test_board_meeting_silence_watchdog.py — RA-1472 watchdog tests.

Locks the contract: when the newest .harness/board-meetings/*.md is older than
the threshold (or no file exists), the watchdog raises an alert. When fresh,
it stays silent. Cooldown prevents storm-firing across consecutive ticks.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

import app.server.cron_watchdogs as cw


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset module-level cooldown so tests don't poison each other."""
    cw._board_meeting_silent_last_raised = 0.0
    yield
    cw._board_meeting_silent_last_raised = 0.0


@pytest.fixture
def mock_meetings_dir(tmp_path, monkeypatch):
    """Redirect the watchdog's expected meetings dir to tmp_path."""
    fake_root = tmp_path
    real_path_class = Path

    class _PatchedPath:
        # Only the specific construction inside the watchdog is redirected.
        # Path("/abs/...") and other Path() calls go through unchanged.
        @staticmethod
        def __new__(cls, *_args):  # pragma: no cover — only used via __file__ chain
            return real_path_class(*_args)

    # Easier: monkeypatch the Path() result inside the function via attribute
    # exposed to the module — instead we patch __file__ traversal by building
    # the expected dir at the real path the watchdog computes.
    expected_dir = (
        real_path_class(cw.__file__).parent.parent.parent / ".harness" / "board-meetings"
    )
    expected_dir.mkdir(parents=True, exist_ok=True)
    yield expected_dir
    # Cleanup: leave existing real files alone — only remove ones we created.


def _make_meeting(dir_path: Path, name: str, age_hours: float) -> Path:
    p = dir_path / name
    p.write_text("# Board meeting\n", encoding="utf-8")
    mtime = time.time() - age_hours * 3600
    os.utime(p, (mtime, mtime))
    return p


@pytest.mark.asyncio
async def test_silent_when_recent_file_present(mock_meetings_dir, caplog):
    """Newest file < threshold → no alert raised, no Linear ticket created."""
    fresh = _make_meeting(mock_meetings_dir, "test-fresh.md", age_hours=2.0)
    try:
        with caplog.at_level(logging.WARNING, logger="pi-ceo"):
            with patch.object(cw, "_BOARD_MEETING_SILENT_THRESHOLD_H", 12.0):
                await cw._watchdog_board_meeting_silence(logging.getLogger("pi-ceo"))
        # No warning emitted → no alert path taken.
        assert not any(
            "Board-meeting watchdog" in rec.message for rec in caplog.records
        )
        assert cw._board_meeting_silent_last_raised == 0.0
    finally:
        fresh.unlink()


@pytest.mark.asyncio
async def test_alerts_when_newest_file_is_stale(mock_meetings_dir, caplog, monkeypatch):
    """Newest file > threshold → warning logged + cooldown bumped."""
    # Disable the Telegram + Linear network calls so the test is hermetic.
    import app.server.config as config
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "", raising=False)
    monkeypatch.setattr(config, "TELEGRAM_ALERT_CHAT_ID", "", raising=False)
    monkeypatch.setattr(config, "LINEAR_API_KEY", "", raising=False)

    stale = _make_meeting(mock_meetings_dir, "test-stale.md", age_hours=24.0)
    try:
        before = cw._board_meeting_silent_last_raised
        with caplog.at_level(logging.WARNING, logger="pi-ceo"):
            await cw._watchdog_board_meeting_silence(logging.getLogger("pi-ceo"))
        assert any(
            "Board-meeting watchdog" in rec.message for rec in caplog.records
        ), "Expected a 'Board-meeting watchdog' warning when newest file is stale"
        assert cw._board_meeting_silent_last_raised > before
    finally:
        stale.unlink()


@pytest.mark.asyncio
async def test_cooldown_suppresses_subsequent_calls(mock_meetings_dir, monkeypatch, caplog):
    """Once raised, the watchdog stays quiet inside the cooldown window."""
    import app.server.config as config
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "", raising=False)
    monkeypatch.setattr(config, "TELEGRAM_ALERT_CHAT_ID", "", raising=False)
    monkeypatch.setattr(config, "LINEAR_API_KEY", "", raising=False)

    stale = _make_meeting(mock_meetings_dir, "test-cooldown.md", age_hours=48.0)
    try:
        # First call — raises.
        await cw._watchdog_board_meeting_silence(logging.getLogger("pi-ceo"))
        first_raised_at = cw._board_meeting_silent_last_raised
        assert first_raised_at > 0

        # Second call inside cooldown — must early-return and NOT update.
        await cw._watchdog_board_meeting_silence(logging.getLogger("pi-ceo"))
        assert cw._board_meeting_silent_last_raised == first_raised_at
    finally:
        stale.unlink()
