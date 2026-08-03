"""
test_board_meeting_producer_ra7085.py — the representative producer.

Proves the board_meeting job AUTHORS its own last-success record: an `ok`
record only on a genuine successful run, and a `failed` record on the failure
path (before re-raising). This is the write side of the RA-7085 contract the
silence watchdog reads.
"""
from __future__ import annotations

import logging
import sys
import types

import pytest

import app.server.cron_fire_agents as cfa
import app.server.job_success_record as jsr
from app.server.cron_fire_agents import _BOARD_MEETING_JOB_ID

_LOG = logging.getLogger("test")


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    # Private success-record store.
    monkeypatch.setattr(jsr, "_job_success_dir", lambda: tmp_path / "job-success")
    # Skip the LLM pre-brief + its persistence.
    async def _no_prebrief(*a, **k):
        return None
    monkeypatch.setattr(cfa, "_generate_board_prebrief", lambda log: None)
    # Silence Telegram/Linear by clearing secrets.
    import app.server.config as config
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "", raising=False)
    monkeypatch.setattr(config, "TELEGRAM_ALERT_CHAT_ID", "", raising=False)
    yield


def _install_board_meeting_stub(monkeypatch, run_impl):
    """Inject a fake app.server.agents.board_meeting so the producer's local
    `from .agents.board_meeting import run_full_board_meeting` resolves to our
    stub without importing the real (heavy) module."""
    stub = types.ModuleType("app.server.agents.board_meeting")
    stub.run_full_board_meeting = run_impl
    monkeypatch.setitem(sys.modules, "app.server.agents.board_meeting", stub)


@pytest.mark.asyncio
async def test_success_authors_ok_record(monkeypatch):
    _install_board_meeting_stub(
        monkeypatch,
        lambda: {"swot": {}, "sprint_recommendations": {}, "gap_audit": {},
                 "status": {}, "duration_s": 1.0},
    )
    await cfa._fire_board_meeting_trigger({"id": "board-meeting-daily"}, _LOG)

    v = jsr.job_health(_BOARD_MEETING_JOB_ID, threshold_h=30.0)
    assert v.state == jsr.HEALTHY
    assert v.record["status"] == jsr.STATUS_OK


@pytest.mark.asyncio
async def test_failure_authors_failed_record_and_reraises(monkeypatch):
    def _boom():
        raise RuntimeError("board meeting exploded")
    _install_board_meeting_stub(monkeypatch, _boom)
    # Don't write a real failure artefact into the repo .harness.
    monkeypatch.setattr(cfa, "_persist_board_meeting_failure", lambda *a, **k: None)

    with pytest.raises(RuntimeError, match="exploded"):
        await cfa._fire_board_meeting_trigger({"id": "board-meeting-daily"}, _LOG)

    rec = jsr.read_record(_BOARD_MEETING_JOB_ID)
    assert rec is not None and rec["status"] == jsr.STATUS_FAILED
    # A failed record is explicitly non-healthy.
    assert jsr.job_health(_BOARD_MEETING_JOB_ID, threshold_h=30.0).state == jsr.FAILED
