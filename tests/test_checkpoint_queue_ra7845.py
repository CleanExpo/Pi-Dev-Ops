"""RA-7845 — the Supabase session checkpoint must not block the event loop.

Production froze for 2.4 s inside `_phase_sandbox -> persistence.save_session`
waiting on Supabase. On the loop the write is now queued to one worker thread;
off the loop it stays synchronous.
"""
from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

from app.server import checkpoint_queue, persistence, supabase_log


def _session(sid: str = "sid-ra7845", status: str = "running") -> SimpleNamespace:
    return SimpleNamespace(id=sid, repo_url="https://github.com/CleanExpo/Pi-Dev-Ops",
                           status=status, output_lines=[], workspace="/tmp/ws",
                           started_at=1700000000.0, error="")


def test_save_on_the_loop_returns_before_the_write_finishes(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(persistence.config, "LOG_DIR", str(tmp_path))
    release = threading.Event()
    rows: list[dict] = []

    def slow_upsert(table: str, row: dict) -> bool:
        release.wait(5)
        rows.append(row)
        return True

    async def save_on_loop() -> float:
        start = time.monotonic()
        persistence.save_session(_session())
        return time.monotonic() - start

    with patch.object(supabase_log, "_upsert", side_effect=slow_upsert):
        elapsed = asyncio.run(save_on_loop())
        assert elapsed < 1.0
        assert rows == []
        release.set()
        assert checkpoint_queue.wait_idle()
    assert [r["id"] for r in rows] == ["sid-ra7845"]


def test_queued_row_is_the_state_at_save_time(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(persistence.config, "LOG_DIR", str(tmp_path))
    rows: list[dict] = []
    session = _session(status="running")

    async def save_then_mutate() -> None:
        persistence.save_session(session)
        session.status = "complete"

    with patch.object(supabase_log, "_upsert", side_effect=lambda t, r: rows.append(r) or True):
        asyncio.run(save_then_mutate())
        assert checkpoint_queue.wait_idle()
    assert rows[0]["status"] == "running"


def test_saves_that_pile_up_collapse_to_the_newest_row(monkeypatch) -> None:
    release = threading.Event()
    rows: list[dict] = []

    def upsert(table: str, row: dict) -> bool:
        release.wait(5)
        rows.append(row)
        return True

    async def burst() -> None:
        checkpoint_queue.save_checkpoint(_session("sid-a", "planning"))  # starts, blocks
        await asyncio.sleep(0.05)
        for status in ("sandbox", "generate", "evaluate"):
            checkpoint_queue.save_checkpoint(_session("sid-a", status))

    with patch.object(supabase_log, "_upsert", side_effect=upsert):
        asyncio.run(burst())
        release.set()
        assert checkpoint_queue.wait_idle()
    assert [r["status"] for r in rows] == ["planning", "evaluate"]


def test_off_the_loop_the_write_stays_synchronous() -> None:
    with patch.object(supabase_log, "save_session_checkpoint", return_value=True) as sync_write:
        checkpoint_queue.save_checkpoint(_session())
    sync_write.assert_called_once()


def test_a_failed_queued_write_is_swallowed() -> None:
    async def save() -> None:
        checkpoint_queue.save_checkpoint(_session())

    with patch.object(supabase_log, "_upsert", side_effect=RuntimeError("supabase down")):
        asyncio.run(save())
        assert checkpoint_queue.wait_idle()
