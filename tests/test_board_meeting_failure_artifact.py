"""tests/test_board_meeting_failure_artifact.py — RA-1984 regression.

`_fire_board_meeting_trigger` must:

  * On exception from `run_full_board_meeting()`, write a `<DATE>-board-failure.md`
    artifact under `.harness/board-meetings/` with the traceback.
  * Re-raise the original exception so the cron-loop's `last_fired_at`
    non-update contract (RA-1484/1493/1497) is preserved — the stale timestamp
    is the operator signal.
  * On success, NOT write a failure artifact (no behavioural change).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.server import cron_fire_agents as cfa


_LOG = logging.getLogger("test")


def test_persist_board_meeting_failure_writes_artifact(tmp_path, monkeypatch):
    """Direct test of the side-effect helper: writes a markdown file with traceback."""
    fake_module_file = tmp_path / "app" / "server" / "cron_fire_agents.py"
    fake_module_file.parent.mkdir(parents=True, exist_ok=True)
    fake_module_file.write_text("# fake", encoding="utf-8")
    monkeypatch.setattr(cfa, "__file__", str(fake_module_file))

    try:
        raise RuntimeError("simulated phase 3 SDK 401")
    except RuntimeError as exc:
        cfa._persist_board_meeting_failure("board-meeting-daily", exc, _LOG)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = tmp_path / ".harness" / "board-meetings"
    written = out_dir / f"{today}-board-failure.md"
    assert written.exists(), f"failure artifact missing: {written}"

    content = written.read_text(encoding="utf-8")
    assert "RuntimeError" in content
    assert "simulated phase 3 SDK 401" in content
    assert "Traceback" in content
    assert "board-meeting-daily" in content


def test_persist_board_meeting_failure_never_raises(tmp_path, monkeypatch):
    """If the artifact write itself fails (e.g. permission denied), the helper
    must log a warning and return cleanly — never raise."""
    fake_module_file = tmp_path / "app" / "server" / "cron_fire_agents.py"
    fake_module_file.parent.mkdir(parents=True, exist_ok=True)
    fake_module_file.write_text("# fake", encoding="utf-8")
    monkeypatch.setattr(cfa, "__file__", str(fake_module_file))

    real_path = cfa.Path

    class _UnwriteablePath(real_path):  # type: ignore[misc, valid-type]
        def mkdir(self, *_a, **_kw):
            raise PermissionError("simulated read-only fs")

    monkeypatch.setattr(cfa, "Path", _UnwriteablePath)

    try:
        raise ValueError("original phase failure")
    except ValueError as exc:
        cfa._persist_board_meeting_failure("board-meeting-daily", exc, _LOG)


@pytest.mark.asyncio
async def test_fire_board_meeting_trigger_persists_artifact_then_reraises(tmp_path, monkeypatch):
    """End-to-end: when run_full_board_meeting raises, the wrapper writes the
    artifact AND re-raises so the cron-loop sees the failure."""
    fake_module_file = tmp_path / "app" / "server" / "cron_fire_agents.py"
    fake_module_file.parent.mkdir(parents=True, exist_ok=True)
    fake_module_file.write_text("# fake", encoding="utf-8")
    monkeypatch.setattr(cfa, "__file__", str(fake_module_file))

    def _raises():
        raise RuntimeError("simulated SDK 401 from phase 3")

    with patch("app.server.agents.board_meeting.run_full_board_meeting", side_effect=_raises):
        with pytest.raises(RuntimeError, match="simulated SDK 401"):
            await cfa._fire_board_meeting_trigger({"id": "board-meeting-daily"}, _LOG)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    written = tmp_path / ".harness" / "board-meetings" / f"{today}-board-failure.md"
    assert written.exists(), f"failure artifact missing: {written}"
    body = written.read_text(encoding="utf-8")
    assert "RuntimeError" in body
    assert "simulated SDK 401" in body
