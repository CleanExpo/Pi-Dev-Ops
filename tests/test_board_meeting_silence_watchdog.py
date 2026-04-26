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

import pytest

import app.server.cron_watchdogs as cw


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset module-level cooldown so tests don't poison each other."""
    cw._board_meeting_silent_last_raised = 0.0
    yield
    cw._board_meeting_silent_last_raised = 0.0


@pytest.fixture
def isolated_meetings_dir(tmp_path, monkeypatch):
    """Redirect the watchdog at a tmp_path it owns alone — no real files."""
    fake_dir = tmp_path / "board-meetings"
    fake_dir.mkdir()
    monkeypatch.setattr(cw, "_board_meetings_dir", lambda: fake_dir)
    yield fake_dir


@pytest.fixture
def _hush_network(monkeypatch):
    """Make Telegram + Linear calls silent no-ops via empty config secrets."""
    import app.server.config as config
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "", raising=False)
    monkeypatch.setattr(config, "TELEGRAM_ALERT_CHAT_ID", "", raising=False)
    monkeypatch.setattr(config, "LINEAR_API_KEY", "", raising=False)


def _make_meeting(dir_path: Path, name: str, age_hours: float) -> Path:
    p = dir_path / name
    p.write_text("# Board meeting\n", encoding="utf-8")
    mtime = time.time() - age_hours * 3600
    os.utime(p, (mtime, mtime))
    return p


@pytest.mark.asyncio
async def test_silent_when_recent_file_present(isolated_meetings_dir, _hush_network, caplog):
    """Newest file < threshold → no alert raised."""
    _make_meeting(isolated_meetings_dir, "fresh.md", age_hours=2.0)
    with caplog.at_level(logging.WARNING, logger="pi-ceo"):
        await cw._watchdog_board_meeting_silence(logging.getLogger("pi-ceo"))
    assert not any("Board-meeting watchdog" in rec.message for rec in caplog.records)
    assert cw._board_meeting_silent_last_raised == 0.0


@pytest.mark.asyncio
async def test_alerts_when_newest_file_is_stale(isolated_meetings_dir, _hush_network, caplog):
    """Newest file > threshold → warning logged + cooldown bumped."""
    _make_meeting(isolated_meetings_dir, "stale.md", age_hours=24.0)
    before = cw._board_meeting_silent_last_raised
    with caplog.at_level(logging.WARNING, logger="pi-ceo"):
        await cw._watchdog_board_meeting_silence(logging.getLogger("pi-ceo"))
    assert any(
        "Board-meeting watchdog" in rec.message for rec in caplog.records
    ), "Expected a 'Board-meeting watchdog' warning when newest file is stale"
    assert cw._board_meeting_silent_last_raised > before


@pytest.mark.asyncio
async def test_alerts_when_dir_is_empty(isolated_meetings_dir, _hush_network, caplog):
    """Empty meetings dir → silence_h is infinity → alert fires."""
    # isolated_meetings_dir is fresh and empty by construction
    before = cw._board_meeting_silent_last_raised
    with caplog.at_level(logging.WARNING, logger="pi-ceo"):
        await cw._watchdog_board_meeting_silence(logging.getLogger("pi-ceo"))
    assert any("never written" in rec.message for rec in caplog.records)
    assert cw._board_meeting_silent_last_raised > before


@pytest.mark.asyncio
async def test_cooldown_suppresses_subsequent_calls(isolated_meetings_dir, _hush_network):
    """Once raised, the watchdog stays quiet inside the cooldown window."""
    _make_meeting(isolated_meetings_dir, "stale.md", age_hours=48.0)

    # First call — raises.
    await cw._watchdog_board_meeting_silence(logging.getLogger("pi-ceo"))
    first_raised_at = cw._board_meeting_silent_last_raised
    assert first_raised_at > 0

    # Second call inside cooldown — must early-return and NOT update.
    await cw._watchdog_board_meeting_silence(logging.getLogger("pi-ceo"))
    assert cw._board_meeting_silent_last_raised == first_raised_at
