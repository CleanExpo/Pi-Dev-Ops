"""
test_board_meeting_silence_watchdog.py — RA-1472 / RA-7030 / RA-7085 tests.

Locks the CURRENT contract (RA-7085 fleet-reliability hardening): the board-
meeting silence watchdog's health signal is the board_meeting job's OWN
last-success record (``job_success_record``, authored only on a genuine
successful run) plus the durable trigger ``last_fired_at`` — never the mtime
of the newest ``.harness/board-meetings/*.md`` file. A missed / failed /
skipped run authors no fresh ``ok`` record, so silence is not masked by a
leftover or deploy-restored artefact file. Cooldown prevents storm-firing.

Before RA-7085 this file asserted the opposite (a recent *file* proved
health). ``test_recent_file_alone_does_not_suppress`` is the regression proof
that the mtime-trusting behaviour is gone.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import pytest

import app.server.cron_watchdogs as cw
import app.server.job_success_record as jsr
from app.server.cron_fire_agents import _BOARD_MEETING_JOB_ID


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset module-level cooldown so tests don't poison each other."""
    cw._board_meeting_silent_last_raised = 0.0
    yield
    cw._board_meeting_silent_last_raised = 0.0


@pytest.fixture
def isolated_success_dir(tmp_path, monkeypatch):
    """Point the job-authored success-record store at a private tmp dir."""
    d = tmp_path / "job-success"
    d.mkdir()
    monkeypatch.setattr(jsr, "_job_success_dir", lambda: d)
    yield d


@pytest.fixture
def isolated_meetings_dir(tmp_path, monkeypatch):
    """Own the artefact dir so mtime-based writes (which must be IGNORED) go
    to tmp, never the real repo."""
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


def _write_record(status: str, age_hours: float) -> None:
    jsr.record(_BOARD_MEETING_JOB_ID, status, ts=time.time() - age_hours * 3600)


def _make_meeting(dir_path: Path, name: str, age_hours: float) -> Path:
    p = dir_path / name
    p.write_text("# Board meeting\n", encoding="utf-8")
    mtime = time.time() - age_hours * 3600
    os.utime(p, (mtime, mtime))
    return p


def _alerted(caplog) -> bool:
    return any("Board-meeting watchdog" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_fresh_success_record_suppresses(
    isolated_success_dir, isolated_meetings_dir, _hush_network, caplog
):
    """A fresh job-authored `ok` record < threshold → healthy → no alert."""
    _write_record(jsr.STATUS_OK, age_hours=2.0)
    with caplog.at_level(logging.WARNING, logger="pi-ceo"):
        await cw._watchdog_board_meeting_silence(logging.getLogger("pi-ceo"))
    assert not _alerted(caplog)
    assert cw._board_meeting_silent_last_raised == 0.0


@pytest.mark.asyncio
async def test_recent_file_alone_does_not_suppress(
    isolated_success_dir, isolated_meetings_dir, _hush_network, caplog
):
    """RA-7085 REGRESSION PROOF (mutation-sensitive).

    A FRESH `.harness/board-meetings/*.md` file exists but NO job-authored
    success record and NO trigger. Under the old mtime-trusting code this
    suppressed the alert (a leftover/deploy-restored file read as healthy —
    the RA-6902 / RA-1469 / RA-7085 bug). Under the job-authored contract the
    file is ignored, the record is MISSING, and the watchdog MUST fire.
    """
    _make_meeting(isolated_meetings_dir, "fresh.md", age_hours=2.0)  # must be ignored
    with caplog.at_level(logging.WARNING, logger="pi-ceo"):
        await cw._watchdog_board_meeting_silence(logging.getLogger("pi-ceo"))
    assert _alerted(caplog), (
        "A recent artefact file must NOT prove health — only a job-authored "
        "success record or fresh trigger does (RA-7085)"
    )
    assert any("never recorded" in rec.message for rec in caplog.records)
    assert cw._board_meeting_silent_last_raised > 0


@pytest.mark.asyncio
async def test_stale_success_record_alerts(
    isolated_success_dir, isolated_meetings_dir, _hush_network, caplog
):
    """An `ok` record older than the threshold (Missed / Late) → alert."""
    _write_record(jsr.STATUS_OK, age_hours=48.0)
    with caplog.at_level(logging.WARNING, logger="pi-ceo"):
        await cw._watchdog_board_meeting_silence(logging.getLogger("pi-ceo"))
    assert _alerted(caplog)
    assert cw._board_meeting_silent_last_raised > 0


@pytest.mark.asyncio
async def test_stale_record_with_fresh_file_not_masked(
    isolated_success_dir, isolated_meetings_dir, _hush_network, caplog
):
    """Task's key case: a STALE record next to a FRESH file must still alert —
    the fresh file must not mask the stale genuine-success signal."""
    _write_record(jsr.STATUS_OK, age_hours=200.0)
    _make_meeting(isolated_meetings_dir, "fresh.md", age_hours=1.0)  # must be ignored
    with caplog.at_level(logging.WARNING, logger="pi-ceo"):
        await cw._watchdog_board_meeting_silence(logging.getLogger("pi-ceo"))
    assert _alerted(caplog)


@pytest.mark.asyncio
async def test_missing_record_alerts(
    isolated_success_dir, isolated_meetings_dir, _hush_network, caplog
):
    """No record at all (job never ran) → MISSING → alert ('never recorded')."""
    with caplog.at_level(logging.WARNING, logger="pi-ceo"):
        await cw._watchdog_board_meeting_silence(logging.getLogger("pi-ceo"))
    assert any("never recorded" in rec.message for rec in caplog.records)
    assert cw._board_meeting_silent_last_raised > 0


@pytest.mark.asyncio
async def test_far_future_record_does_not_suppress(
    isolated_success_dir, isolated_meetings_dir, _hush_network, caplog
):
    """Codex P1 regression — a bogus far-future `ok` record must NOT clamp to
    age 0 and suppress the alert. The watchdog must still fire (record rejected
    as not-credible, so silence stays unproven)."""
    _write_record(jsr.STATUS_OK, age_hours=-24 * 365)  # one year in the FUTURE
    with caplog.at_level(logging.WARNING, logger="pi-ceo"):
        await cw._watchdog_board_meeting_silence(logging.getLogger("pi-ceo"))
    assert _alerted(caplog), "a far-future record must not mask silence"
    assert cw._board_meeting_silent_last_raised > 0


@pytest.mark.asyncio
async def test_huge_int_ts_record_does_not_crash_watchdog(
    isolated_success_dir, isolated_meetings_dir, _hush_network, caplog
):
    """Codex re-review P1 regression — a record with a ts too large for float()
    (10**400) must not raise out of the watchdog (which would skip the alert AND
    every later watchdog that cycle). The record is rejected → watchdog alerts."""
    (isolated_success_dir / f"{_BOARD_MEETING_JOB_ID}.json").write_text(
        '{"job_id": "' + _BOARD_MEETING_JOB_ID + '", "status": "ok", "ts": '
        + "1" + "0" * 400 + "}",
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING, logger="pi-ceo"):
        # Must not raise.
        await cw._watchdog_board_meeting_silence(logging.getLogger("pi-ceo"))
    assert _alerted(caplog), "an uninterpretable ts must not mask silence"
    assert cw._board_meeting_silent_last_raised > 0


@pytest.mark.asyncio
async def test_failed_record_alerts(
    isolated_success_dir, isolated_meetings_dir, _hush_network, caplog
):
    """A fresh `failed` record is an explicit non-success → alert, never
    masked as healthy just because it is recent."""
    _write_record(jsr.STATUS_FAILED, age_hours=0.5)
    with caplog.at_level(logging.WARNING, logger="pi-ceo"):
        await cw._watchdog_board_meeting_silence(logging.getLogger("pi-ceo"))
    assert _alerted(caplog)
    assert cw._board_meeting_silent_last_raised > 0


@pytest.mark.asyncio
async def test_cooldown_suppresses_subsequent_calls(
    isolated_success_dir, isolated_meetings_dir, _hush_network
):
    """Once raised, the watchdog stays quiet inside the cooldown window."""
    # No record → MISSING → first call raises.
    await cw._watchdog_board_meeting_silence(logging.getLogger("pi-ceo"))
    first_raised_at = cw._board_meeting_silent_last_raised
    assert first_raised_at > 0

    # Second call inside cooldown — must early-return and NOT update.
    await cw._watchdog_board_meeting_silence(logging.getLogger("pi-ceo"))
    assert cw._board_meeting_silent_last_raised == first_raised_at


@pytest.mark.asyncio
async def test_fresh_trigger_fire_suppresses_alert_despite_no_record(
    isolated_success_dir, isolated_meetings_dir, _hush_network, caplog
):
    """RA-7030: a recently-fired board_meeting trigger proves liveness even
    with no job-authored record yet (durable signal survives Railway redeploy
    where the container filesystem — and any fresh record — is reset)."""
    triggers = [{
        "type": "board_meeting",
        "enabled": True,
        "last_fired_at": time.time() - 2 * 3600,
    }]
    with caplog.at_level(logging.WARNING, logger="pi-ceo"):
        await cw._watchdog_board_meeting_silence(logging.getLogger("pi-ceo"), triggers)
    assert not _alerted(caplog)
    assert cw._board_meeting_silent_last_raised == 0.0


@pytest.mark.asyncio
async def test_stale_trigger_and_no_record_still_alert(
    isolated_success_dir, isolated_meetings_dir, _hush_network, caplog
):
    """RA-7030: a long-dead trigger must not mask genuine silence."""
    triggers = [{
        "type": "board_meeting",
        "enabled": True,
        "last_fired_at": time.time() - 100 * 3600,
    }]
    with caplog.at_level(logging.WARNING, logger="pi-ceo"):
        await cw._watchdog_board_meeting_silence(logging.getLogger("pi-ceo"), triggers)
    assert _alerted(caplog)
